import json
import io
import sqlite3
import tempfile
import tarfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.backup_database import backup_database
from scripts.cloud_backup import make_archive
from scripts.export_training import merge_jsonl
from src.health import check_heartbeat, write_heartbeat
from src.storage import MessageStore, SourcePost


class OperationsTests(unittest.TestCase):
    def test_training_corpus_keeps_old_posts_and_updates_edits(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory) / "messages.sqlite3"
            store = MessageStore(data)
            try:
                store.record(SourcePost(1, 2, "demo_source", "2026-09-27T09:00:00+00:00", "Новий текст"))
                old = {"channel_id": 1, "message_id": 1, "channel_username": "demo_source",
                       "posted_at": "2026-09-26T09:00:00+00:00", "text": "Старий пост"}
                edited = {"channel_id": 1, "message_id": 2, "channel_username": "demo_source",
                          "posted_at": "2026-09-27T09:00:00+00:00", "text": "Попередня версія"}
                corpus, count = merge_jsonl((json.dumps(old) + "\n" + json.dumps(edited) + "\n").encode(), data)
                records = [json.loads(line) for line in corpus.decode().splitlines()]
                self.assertEqual(count, 2)
                self.assertEqual([row["text"] for row in records], ["Старий пост", "Новий текст"])
                self.assertEqual(records[1]["source_url"], "https://t.me/demo_source/2")
            finally:
                store.close()

    def test_cloud_archive_contains_consistent_database_and_session(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            for name in ("messages.sqlite3", "telegram.session"):
                with closing(sqlite3.connect(data / name)) as connection:
                    connection.execute("CREATE TABLE sample (value TEXT)")
                    connection.execute("INSERT INTO sample VALUES (?)", (name,))
                    connection.commit()
            archive_bytes = make_archive(data)
            with tempfile.TemporaryDirectory() as restore_directory:
                with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as archive:
                    self.assertEqual(sorted(archive.getnames()), ["messages.sqlite3", "telegram.session"])
                    for member in archive.getmembers():
                        (Path(restore_directory) / member.name).write_bytes(archive.extractfile(member).read())
                for name in ("messages.sqlite3", "telegram.session"):
                    with closing(sqlite3.connect(Path(restore_directory) / name)) as restored:
                        self.assertEqual(restored.execute("SELECT value FROM sample").fetchone()[0], name)

    def test_heartbeat_fresh_and_stale(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "heartbeat.json"
            self.assertFalse(check_heartbeat(path, 120)[0])
            write_heartbeat(path, ["demo_source"])
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["sources"], ["demo_source"])
            timestamp = datetime.fromisoformat(payload["updated_at"])
            self.assertTrue(check_heartbeat(path, 120, now=timestamp + timedelta(seconds=30))[0])
            self.assertFalse(check_heartbeat(path, 120, now=timestamp + timedelta(seconds=121))[0])

    def test_backup_includes_committed_wal_data(self):
        with tempfile.TemporaryDirectory() as directory:
            original = Path(directory) / "messages.sqlite3"
            backup = Path(directory) / "backup.sqlite3"
            store = MessageStore(original)
            try:
                store.record(SourcePost(1, 7, "demo_source",
                                        "2026-09-27T09:00:00+00:00", "Обрана зона чисто"))
                backup_database(original, backup)
                with closing(sqlite3.connect(backup)) as copy:
                    text = copy.execute("SELECT text FROM messages").fetchone()[0]
                self.assertEqual(text, "Обрана зона чисто")
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
