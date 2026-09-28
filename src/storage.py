"""SQLite journal for source posts and their delivery progress."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from src.official_alerts import official_kyiv_alert_state


@dataclass(frozen=True)
class SourcePost:
    channel_id: int
    message_id: int
    channel_username: str
    posted_at: str
    text: str
    reply_to_message_id: int | None = None
    edited_at: str | None = None
    has_media: bool = False
    raw_json: str | None = None


class MessageStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA busy_timeout=5000")
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                channel_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                channel_username TEXT NOT NULL,
                posted_at TEXT NOT NULL,
                text TEXT NOT NULL,
                reply_to_message_id INTEGER,
                edited_at TEXT,
                has_media INTEGER NOT NULL,
                raw_json TEXT,
                delivery_state TEXT NOT NULL,
                sent_chunks INTEGER NOT NULL DEFAULT 0,
                delivered_at TEXT,
                relevance_action TEXT,
                relevance_tier TEXT,
                relevance_reason TEXT,
                routed_at TEXT,
                PRIMARY KEY (channel_id, message_id)
            )
            """
        )
        existing_columns = {
            row["name"] for row in self.connection.execute("PRAGMA table_info(messages)")
        }
        for column in ("relevance_action", "relevance_tier", "relevance_reason", "routed_at"):
            if column not in existing_columns:
                self.connection.execute(f"ALTER TABLE messages ADD COLUMN {column} TEXT")
        self.connection.execute(
            "CREATE INDEX IF NOT EXISTS messages_pending ON messages(delivery_state, posted_at)"
        )
        self.connection.execute(
            """CREATE TABLE IF NOT EXISTS kyiv_alert_status (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                state TEXT NOT NULL,
                checked_at TEXT NOT NULL,
                alert_json TEXT,
                notified_state TEXT
            )"""
        )
        self.connection.execute(
            """CREATE TABLE IF NOT EXISTS kyiv_alert_events (
                id INTEGER PRIMARY KEY,
                state TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                alert_json TEXT
            )"""
        )
        alert_columns = {row["name"] for row in self.connection.execute("PRAGMA table_info(kyiv_alert_status)")}
        if "active_since" not in alert_columns:
            self.connection.execute("ALTER TABLE kyiv_alert_status ADD COLUMN active_since TEXT")
        self.connection.commit()

    def observe_kyiv_alert(self, state: str, checked_at: str, alert_json: str | None) -> bool:
        """Save a valid API observation; return whether the visible state changed."""
        if state not in {"clear", "yellow", "red", "active_unknown"}:
            raise ValueError(f"Invalid Kyiv alert state: {state}")
        previous = self.connection.execute(
            "SELECT state, active_since FROM kyiv_alert_status WHERE id = 1"
        ).fetchone()
        changed = previous is None or previous["state"] != state
        active_since = None if state == "clear" else (
            previous["active_since"] if previous is not None and previous["state"] != "clear" and previous["active_since"]
            else checked_at
        )
        with self.connection:
            self.connection.execute(
                """INSERT INTO kyiv_alert_status (id, state, checked_at, alert_json, notified_state, active_since)
                   VALUES (1, ?, ?, ?, NULL, ?)
                   ON CONFLICT(id) DO UPDATE SET state = excluded.state,
                       checked_at = excluded.checked_at, alert_json = excluded.alert_json,
                       active_since = excluded.active_since,
                       notified_state = CASE WHEN state = excluded.state THEN notified_state ELSE NULL END""",
                (state, checked_at, alert_json, active_since),
            )
            if changed:
                self.connection.execute(
                    "INSERT INTO kyiv_alert_events (state, observed_at, alert_json) VALUES (?, ?, ?)",
                    (state, checked_at, alert_json),
                )
        return changed

    def sync_official_alerts(self, channel: str) -> None:
        current = self.connection.execute("SELECT checked_at, state, active_since FROM kyiv_alert_status WHERE id = 1").fetchone()
        after = current["checked_at"] if current else ""
        rows = self.connection.execute(
            "SELECT text, posted_at FROM messages WHERE lower(channel_username) = ? AND posted_at >= ? ORDER BY posted_at, message_id",
            (channel.casefold(), after),
        ).fetchall()
        for row in rows:
            state = official_kyiv_alert_state(row["text"])
            if state is not None and (row["posted_at"] > after or current is None or state != current["state"]
                                      or (state != "clear" and not current["active_since"])):
                self.observe_kyiv_alert(state, row["posted_at"], None)
                current = self.connection.execute("SELECT checked_at, state, active_since FROM kyiv_alert_status WHERE id = 1").fetchone()
                after = current["checked_at"]

    def active_alert_since(self) -> str | None:
        row = self.connection.execute("SELECT state, active_since FROM kyiv_alert_status WHERE id = 1").fetchone()
        return row["active_since"] if row and row["state"] != "clear" else None

    def recent_notifications(self, since: str, channel_id: int) -> list[sqlite3.Row]:
        return self.connection.execute(
            """SELECT * FROM messages WHERE delivered_at >= ? AND channel_id != ?
               AND delivery_state = 'sent' AND relevance_action = 'notify'
               AND relevance_tier != 'official_status' ORDER BY delivered_at DESC""",
            (since, channel_id),
        ).fetchall()

    def discard_digest(self, rows: list[sqlite3.Row], reason: str) -> None:
        with self.connection:
            self.connection.executemany(
                """UPDATE messages SET delivery_state = 'skipped', relevance_reason = ?
                   WHERE channel_id = ? AND message_id = ? AND delivery_state = 'digest'""",
                [(reason, row["channel_id"], row["message_id"]) for row in rows],
            )

    def pending_kyiv_alert(self) -> sqlite3.Row | None:
        return self.connection.execute(
            "SELECT state, checked_at FROM kyiv_alert_status WHERE id = 1 AND notified_state IS NULL"
        ).fetchone()

    def mark_kyiv_alert_notified(self, state: str) -> None:
        with self.connection:
            self.connection.execute(
                "UPDATE kyiv_alert_status SET notified_state = state WHERE id = 1 AND state = ?",
                (state,),
            )

    def record(self, post: SourcePost, *, historical: bool = False) -> bool:
        """Save a post; return true only when it was not already present."""
        state = "history" if historical else ("pending" if post.text.strip() else "no_text")
        with self.connection:
            cursor = self.connection.execute(
                """
                INSERT INTO messages (
                    channel_id, message_id, channel_username, posted_at, text,
                    reply_to_message_id, edited_at, has_media, raw_json, delivery_state
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(channel_id, message_id) DO NOTHING
                """,
                (
                    post.channel_id,
                    post.message_id,
                    post.channel_username,
                    post.posted_at,
                    post.text,
                    post.reply_to_message_id,
                    post.edited_at,
                    int(post.has_media),
                    post.raw_json,
                    state,
                ),
            )
        return cursor.rowcount == 1

    def record_edit(self, post: SourcePost) -> bool:
        """Save an edit and queue changed text for delivery. Return true if text changed."""
        old = self.connection.execute(
            "SELECT text, delivery_state FROM messages WHERE channel_id = ? AND message_id = ?",
            (post.channel_id, post.message_id),
        ).fetchone()
        if old is None:
            return self.record(post)
        changed = old["text"] != post.text
        state = ("pending" if post.text.strip() else "no_text") if changed else old["delivery_state"]
        with self.connection:
            self.connection.execute(
                """
                UPDATE messages SET text = ?, edited_at = ?, has_media = ?, raw_json = ?,
                    delivery_state = ?, sent_chunks = CASE WHEN ? THEN 0 ELSE sent_chunks END,
                    delivered_at = CASE WHEN ? THEN NULL ELSE delivered_at END,
                    relevance_action = CASE WHEN ? THEN NULL ELSE relevance_action END,
                    relevance_tier = CASE WHEN ? THEN NULL ELSE relevance_tier END,
                    relevance_reason = CASE WHEN ? THEN NULL ELSE relevance_reason END,
                    routed_at = CASE WHEN ? THEN NULL ELSE routed_at END
                WHERE channel_id = ? AND message_id = ?
                """,
                (
                    post.text, post.edited_at, int(post.has_media), post.raw_json,
                    state, *(int(changed),) * 6, post.channel_id, post.message_id,
                ),
            )
        return changed

    def last_id(self, channel_id: int) -> int | None:
        row = self.connection.execute(
            "SELECT MAX(message_id) AS last_id FROM messages WHERE channel_id = ?",
            (channel_id,),
        ).fetchone()
        return row["last_id"]

    def get_post(self, channel_id: int, message_id: int) -> sqlite3.Row | None:
        return self.connection.execute(
            "SELECT * FROM messages WHERE channel_id = ? AND message_id = ?",
            (channel_id, message_id),
        ).fetchone()

    def pending(self) -> list[sqlite3.Row]:
        return self.connection.execute(
            """
            SELECT * FROM messages WHERE delivery_state = 'pending'
            ORDER BY posted_at, channel_id, message_id
            """
        ).fetchall()

    def mark_routed(self, channel_id: int, message_id: int, action: str,
                    tier: str | None, reason: str) -> None:
        if action not in ("notify", "digest", "skip"):
            raise ValueError(f"Invalid relevance action: {action}")
        state = "pending" if action == "notify" else ("digest" if action == "digest" else "skipped")
        now = datetime.now(timezone.utc).isoformat()
        with self.connection:
            self.connection.execute(
                """UPDATE messages SET delivery_state = ?, relevance_action = ?,
                   relevance_tier = ?, relevance_reason = ?, routed_at = ?
                   WHERE channel_id = ? AND message_id = ? AND delivery_state = 'pending'""",
                (state, action, tier, reason, now, channel_id, message_id),
            )

    def digest_pending(self) -> list[sqlite3.Row]:
        return self.connection.execute(
            """SELECT * FROM messages WHERE delivery_state = 'digest'
               ORDER BY routed_at, posted_at, channel_id, message_id"""
        ).fetchall()

    def active_digest_pending(self) -> list[sqlite3.Row]:
        rows = self.digest_pending()
        active_since = self.active_alert_since()
        stale = [row for row in rows if active_since is None or row["posted_at"] < active_since]
        self.discard_digest(stale, "Quiet report outside the current active city alert")
        return [row for row in rows if active_since is not None and row["posted_at"] >= active_since]

    def mark_digest_delivered(self, rows: list[sqlite3.Row]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self.connection:
            self.connection.executemany(
                """UPDATE messages SET delivery_state = 'sent', delivered_at = ?
                   WHERE channel_id = ? AND message_id = ? AND delivery_state = 'digest'""",
                [(now, row["channel_id"], row["message_id"]) for row in rows],
            )

    def mark_chunk_sent(self, channel_id: int, message_id: int, count: int) -> None:
        with self.connection:
            self.connection.execute(
                """
                UPDATE messages SET sent_chunks = ?
                WHERE channel_id = ? AND message_id = ? AND delivery_state = 'pending'
                """,
                (count, channel_id, message_id),
            )

    def mark_delivered(self, channel_id: int, message_id: int) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self.connection:
            self.connection.execute(
                """
                UPDATE messages SET delivery_state = 'sent', delivered_at = ?
                WHERE channel_id = ? AND message_id = ? AND delivery_state = 'pending'
                """,
                (now, channel_id, message_id),
            )

    def close(self) -> None:
        self.connection.close()
