"""Review draft relevance decisions against the local SQLite journal."""

from __future__ import annotations

import argparse
import csv
import sqlite3
from collections import Counter
from pathlib import Path

from src.relevance import RelevanceRules


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config.yaml")
    parser.add_argument("--database", type=Path, default=ROOT / ".local" / "messages.sqlite3")
    parser.add_argument("--output", type=Path, default=ROOT / ".local" / "relevance_review.csv")
    args = parser.parse_args()
    rules = RelevanceRules.from_yaml(args.config)
    database_uri = args.database.resolve().as_uri() + "?mode=ro"
    with sqlite3.connect(database_uri, uri=True) as connection:
        rows = connection.execute(
            """SELECT channel_id, channel_username, message_id, posted_at, text,
                      reply_to_message_id, delivery_state
               FROM messages ORDER BY posted_at, channel_id, message_id"""
        ).fetchall()
    posts_by_id = {(row[0], row[2]): {
        "message_id": row[2], "posted_at": row[3], "text": row[4]
    } for row in rows}

    args.output.parent.mkdir(parents=True, exist_ok=True)
    existing_labels = {}
    if args.output.exists():
        with args.output.open("r", encoding="utf-8-sig", newline="") as file:
            for old in csv.DictReader(file):
                existing_labels[(old["source"], old["message_id"])] = (
                    old.get("my_label", ""), old.get("notes", "")
                )
    counts: Counter[str] = Counter()
    with args.output.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(("source", "message_id", "posted_at", "action", "tier", "places",
                         "reason", "text", "source_url", "current_delivery_state",
                         "my_label", "notes"))
        for channel_id, source, message_id, posted_at, text, reply_to_id, delivery_state in rows:
            parent = posts_by_id.get((channel_id, reply_to_id)) if reply_to_id is not None else None
            decision = rules.classify_with_reply(text, posted_at, parent)
            counts[decision.action] += 1
            my_label, notes = existing_labels.get((source, str(message_id)), ("", ""))
            writer.writerow((source, message_id, posted_at, decision.action,
                             decision.tier or "", "; ".join(decision.places), decision.reason,
                             text, f"https://t.me/{source}/{message_id}", delivery_state,
                             my_label, notes))
    print(f"Reviewed {len(rows)} posts: " + ", ".join(
        f"{action}={counts[action]}" for action in ("notify", "digest", "skip")
    ))
    print(f"CSV: {args.output}")


if __name__ == "__main__":
    main()
