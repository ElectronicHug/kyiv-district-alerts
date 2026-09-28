import tempfile
import unittest
from html import unescape
from pathlib import Path

from src.formatting import digest_message, message_chunks
from src.storage import MessageStore, SourcePost


class MessageStoreTests(unittest.TestCase):
    def test_history_is_not_delivered_and_new_posts_are_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            store = MessageStore(Path(directory) / "messages.sqlite3")
            try:
                old = SourcePost(1, 10, "source", "2026-09-27T09:00:00+00:00", "old")
                new = SourcePost(1, 11, "source", "2026-09-27T09:01:00+00:00", "new")
                self.assertTrue(store.record(old, historical=True))
                self.assertTrue(store.record(new))
                self.assertFalse(store.record(new))
                self.assertEqual(store.last_id(1), 11)
                self.assertEqual(store.get_post(1, 11)["text"], "new")
                self.assertEqual([row["message_id"] for row in store.pending()], [11])
                store.mark_chunk_sent(1, 11, 1)
                self.assertEqual(store.pending()[0]["sent_chunks"], 1)
                store.mark_delivered(1, 11)
                self.assertEqual(store.pending(), [])
                edited = SourcePost(1, 11, "source", "2026-09-27T09:01:00+00:00", "new text",
                                    edited_at="2026-09-27T09:02:00+00:00")
                self.assertTrue(store.record_edit(edited))
                self.assertEqual(store.pending()[0]["text"], "new text")
                self.assertEqual(store.pending()[0]["sent_chunks"], 0)
            finally:
                store.close()
            reopened = MessageStore(Path(directory) / "messages.sqlite3")
            try:
                self.assertEqual(reopened.pending()[0]["message_id"], 11)
                self.assertEqual(reopened.last_id(1), 11)
            finally:
                reopened.close()

    def test_text_is_split_without_loss(self):
        body = "ї" * 9000
        chunks = message_chunks("source", 12, "2026-09-27T09:00:00+00:00", body)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) < 4096 for chunk in chunks))
        self.assertEqual("".join(unescape(chunk.split("\n\n", 2)[1]) for chunk in chunks), body)

    def test_compact_html_alert_escapes_source_text_and_links_context(self):
        chunks = message_chunks(
            "demo_source", 6, "2026-09-27T09:28:35+00:00", "Чисто < & >",
            intro="✅ Чисто · Обрана зона", context_message_id=5,
        )
        self.assertEqual(len(chunks), 1)
        self.assertIn("Чисто &lt; &amp; &gt;", chunks[0])
        self.assertIn("27.09 · 12:28", chunks[0])
        self.assertIn('href="https://t.me/demo_source/5"', chunks[0])

    def test_filtered_routing_and_edit_requeues(self):
        with tempfile.TemporaryDirectory() as directory:
            store = MessageStore(Path(directory) / "messages.sqlite3")
            try:
                post = SourcePost(1, 1, "source", "2026-09-27T09:00:00+00:00", "Київ загалом")
                store.record(post)
                store.mark_routed(1, 1, "digest", "broad", "Київ")
                waiting = store.digest_pending()
                self.assertEqual(len(waiting), 1)
                self.assertIn("https://t.me/source/1", digest_message(waiting))
                store.mark_digest_delivered(waiting)
                self.assertEqual(store.digest_pending(), [])
                edited = SourcePost(1, 1, "source", post.posted_at, "Обрана зона",
                                    edited_at="2026-09-27T09:02:00+00:00")
                self.assertTrue(store.record_edit(edited))
                self.assertEqual(len(store.pending()), 1)
                self.assertIsNone(store.pending()[0]["relevance_action"])
                store.mark_routed(1, 1, "notify", "direct", "Обрана зона")
                self.assertEqual(store.pending()[0]["relevance_action"], "notify")
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
