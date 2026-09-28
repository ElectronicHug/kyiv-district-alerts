import unittest
from pathlib import Path

from src.relevance import RelevanceRules


RULES = RelevanceRules.from_yaml(Path(__file__).resolve().parents[1] / "config.example.yaml")


class RelevanceTests(unittest.TestCase):
    def test_direct_mention(self):
        decision = RULES.classify("Сусідня зона - Демоʼзона ще один")
        self.assertEqual((decision.action, decision.tier), ("notify", "direct"))
        self.assertIn("Обрана зона", decision.places)
        self.assertEqual(RULES.classify("🔻Зниження Обрана зона").tier, "direct")

    def test_nearby_mention(self):
        self.assertEqual(RULES.classify("Сусідня зона на сусідню зону").action, "notify")
        self.assertEqual(RULES.classify("Наступний невідома місцевість, Сусідня зона").action, "notify")
        self.assertEqual(RULES.classify("невідома місцевість, Сусідня зона реактив!").action, "notify")
        self.assertEqual(RULES.classify("Сусідня зона").action, "notify")

    def test_broad_kyiv(self):
        self.assertEqual(RULES.classify("На заліт в Київ, високо.").action, "digest")
        self.assertEqual(RULES.classify("Йде високо мандрувати на Правий").action, "digest")
        self.assertEqual(RULES.classify("Центр лівий на Правий").action, "digest")

    def test_generic_center_alias_excludes_left_center_phrase(self):
        import copy
        rules = copy.deepcopy(RULES)
        rules.places['direct']['Центр'] = ['центр', 'центру', 'центрі']
        self.assertEqual(rules.classify('На центр міста').action, 'notify')
        self.assertEqual(rules.classify('Центр лівий на Правий').action, 'digest')

    def test_local_clear_is_immediate(self):
        self.assertEqual(RULES.classify("Київ чисто.").action, "notify")
        self.assertEqual(RULES.classify("Київщина чисто.").action, "skip")
        local = RULES.classify("Сусідня зона чисто.")
        self.assertEqual(local.action, "notify")
        self.assertTrue(local.is_clear)
        self.assertEqual(RULES.classify("Демоʼзона: відбій").action, "notify")

    def test_mixed_clear_and_new_threat_is_not_labeled_clear(self):
        text = (
            "Локаційно чисто в Києві та області.\n\n"
            "Два нових реактивних Шахеда на Київщину з Чернігівщини."
        )
        decision = RULES.classify(text)
        self.assertEqual(decision.action, "notify")
        self.assertFalse(decision.is_clear)
        self.assertIn("Змішаний", decision.reason)
        self.assertTrue(RULES.classify("Київ - відбій повітряної тривоги! Тривалість 4 год.").is_clear)

    def test_clear_reply_inherits_recent_local_context_only(self):
        parent = {"message_id": 42, "posted_at": "2026-09-27T08:00:00+00:00",
                  "text": "Київ: Обрана зона"}
        result = RULES.classify_with_reply("Чисто", "2026-09-27T08:15:00+00:00", parent)
        self.assertEqual((result.action, result.tier), ("notify", "direct"))
        self.assertEqual(result.context_message_id, 42)
        stale = RULES.classify_with_reply("Чисто", "2026-09-27T15:00:00+00:00", parent)
        self.assertEqual(stale.action, "skip")
        distant = dict(parent, text="Інше місто")
        self.assertEqual(
            RULES.classify_with_reply("Чисто", "2026-09-27T08:15:00+00:00", distant).action,
            "skip",
        )

    def test_no_substring_false_positive(self):
        self.assertEqual(RULES.classify("Київщина дорозвідка до відбою.").action, "skip")
        self.assertEqual(RULES.classify("Демоʼзональний район іншого міста").action, "skip")

    def test_distant_mention(self):
        self.assertEqual(RULES.classify("Інше місто").action, "skip")
        self.assertEqual(RULES.classify("Київ: 🅿️1х Віддалена зона 4км").action, "skip")

    def test_long_editorial_broad_post(self):
        self.assertEqual(RULES.classify("Про Київ і роботу каналу. " * 30).action, "skip")


if __name__ == "__main__":
    unittest.main()
