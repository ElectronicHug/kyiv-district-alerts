import tempfile
import unittest
from pathlib import Path

from src.duplicates import repeated_report
from src.formatting import clean_source_text, message_chunks
from src.relevance import RelevanceRules, Decision
from src.storage import MessageStore, SourcePost


RULES = RelevanceRules.from_yaml(Path(__file__).resolve().parents[1] / "config.example.yaml")


class DeliveryRulesTests(unittest.TestCase):
    def repeats(self, first, second):
        return repeated_report(first, RULES.classify(first), second, RULES.classify(second), RULES)

    def test_center_and_signature(self):
        self.assertEqual(RULES.classify("На обрану зону").action, "notify")
        self.assertEqual(RULES.classify("Центр лівий на Правий").action, "digest")
        text = "🟡🛵Сусідня зона!\n\n@demo_source"
        self.assertEqual(clean_source_text(text), "🟡🛵Сусідня зона!")
        rendered = message_chunks("demo_source", 1, "2026-09-28T09:00:00+00:00", text)[0]
        self.assertEqual(rendered.count("@demo_source"), 1)
        self.assertEqual(clean_source_text("Згадуємо @demo_source у тексті"), "Згадуємо @demo_source у тексті")

    def test_cross_channel_brief_repeats_and_distinct_details(self):
        self.assertTrue(self.repeats("Київ: 🔻Зниження Обрана зона", "Демоʼзона падає"))
        self.assertTrue(self.repeats("Київ: 🔻Зниження Обрана зона", "🟡🛵Демоʼзона\n\n@demo_source"))
        self.assertTrue(self.repeats("Сусідня зона", "🟡🛵Сусідня зона!"))
        for other in ("Обрана зона чисто", "Обрана зона ще один", "Обрана зона 2х",
                      "Обрана зона невідома місцевість", "Обрана зона ракета", "🚀Обрана зона", "Сусідня зона"):
            self.assertFalse(self.repeats("Обрана зона", other), other)
        self.assertFalse(repeated_report("Чисто", Decision("notify", "direct", ("Друга зона",), "", True),
                                         "Чисто", Decision("notify", "direct", ("Центр",), "", True), RULES))

    def test_official_alert_gates_digest_and_clears_old_queue(self):
        with tempfile.TemporaryDirectory() as directory:
            store = MessageStore(Path(directory) / "messages.sqlite3")
            try:
                def report(message_id, at):
                    store.record(SourcePost(1, message_id, "source", at, "Київ"))
                    store.mark_routed(1, message_id, "digest", "broad", "test")
                report(1, "2026-09-28T08:00:00+00:00")
                self.assertEqual(store.active_digest_pending(), [])  # unknown state
                store.record(SourcePost(2, 10, "va_kyiv", "2026-09-28T08:05:00+00:00",
                                        "🟡 Жовтий рівень небезпеки"), historical=True)
                store.sync_official_alerts("va_kyiv")
                report(2, "2026-09-28T08:10:00+00:00")
                self.assertEqual(len(store.active_digest_pending()), 1)
                store.record(SourcePost(2, 11, "va_kyiv", "2026-09-28T08:15:00+00:00",
                                        "🔴 Червоний рівень небезпеки"))
                store.sync_official_alerts("va_kyiv")
                self.assertEqual(store.active_alert_since(), "2026-09-28T08:05:00+00:00")
                store.record(SourcePost(2, 12, "va_kyiv", "2026-09-28T08:20:00+00:00",
                                        "🟢 Відбій повітряної тривоги."))
                store.sync_official_alerts("va_kyiv")
                self.assertEqual(store.active_digest_pending(), [])
                self.assertEqual(store.get_post(1, 2)["delivery_state"], "skipped")
                store.sync_official_alerts("va_kyiv")
                self.assertEqual(store.connection.execute("SELECT count(*) FROM kyiv_alert_events").fetchone()[0], 3)
                store.record(SourcePost(2, 13, "va_kyiv", "2026-09-28T08:30:00+00:00",
                                        "🟡 Жовтий рівень небезпеки"))
                store.sync_official_alerts("va_kyiv")
                store.record_edit(SourcePost(2, 13, "va_kyiv", "2026-09-28T08:30:00+00:00",
                                             "🟢 Відбій повітряної тривоги.", edited_at="2026-09-28T08:31:00+00:00"))
                store.sync_official_alerts("va_kyiv")
                self.assertIsNone(store.active_alert_since())
            finally:
                store.close()

    def test_duplicate_candidates_survive_restart_and_exclude_same_channel(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "messages.sqlite3"
            store = MessageStore(path)
            store.record(SourcePost(1, 1, "source", "2026-09-28T08:00:00+00:00", "Обрана зона"))
            store.mark_routed(1, 1, "notify", "direct", "test")
            store.mark_delivered(1, 1)
            store.close()
            store = MessageStore(path)
            try:
                self.assertEqual(len(store.recent_notifications("2026-09-28T00:00:00+00:00", 2)), 1)
                self.assertEqual(store.recent_notifications("2026-09-28T00:00:00+00:00", 1), [])
                self.assertEqual(store.recent_notifications("2099-09-28T00:00:00+00:00", 2), [])
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
