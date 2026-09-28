"""Keep one cumulative UTF-8 JSONL file of every collected source post."""

from __future__ import annotations

import argparse
import json
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from scripts.backup_database import backup_database
from scripts.gcp_common import access_token, post


ROOT = Path(__file__).resolve().parents[1]
OBJECT_NAME = "messages.jsonl"


def object_url(bucket: str) -> str:
    return f"https://storage.googleapis.com/storage/v1/b/{quote(bucket, safe='')}/o/{quote(OBJECT_NAME, safe='')}"


def existing_file(bucket: str) -> tuple[bytes, str]:
    url = object_url(bucket)
    headers = {"Authorization": f"Bearer {access_token()}"}
    try:
        with urlopen(Request(url + "?fields=generation", headers=headers), timeout=60) as response:
            generation = json.load(response)["generation"]
    except HTTPError as error:
        if error.code == 404:
            return b"", "0"
        raise
    with urlopen(Request(url + f"?alt=media&generation={generation}", headers=headers), timeout=120) as response:
        return response.read(), generation


def merge_jsonl(previous: bytes, database: Path) -> tuple[bytes, int]:
    rows: dict[tuple[int, int], dict] = {}
    for line in previous.decode("utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            key = (int(row["channel_id"]), int(row["message_id"]))
            if key in rows:
                raise ValueError(f"Duplicate source post in existing corpus: {key}")
            rows[key] = row
    previous_count = len(rows)
    with tempfile.TemporaryDirectory() as directory:
        snapshot = Path(directory) / "messages.sqlite3"
        backup_database(database, snapshot)
        with closing(sqlite3.connect(snapshot)) as connection:
            connection.row_factory = sqlite3.Row
            for record in connection.execute("SELECT * FROM messages"):
                row = dict(record)
                row["source_url"] = f"https://t.me/{row['channel_username']}/{row['message_id']}"
                key = (row["channel_id"], row["message_id"])
                previous_row = rows.get(key)
                if previous_row is None or (row.get("edited_at") or row["posted_at"]) >= (previous_row.get("edited_at") or previous_row["posted_at"]):
                    rows[key] = row
    if len(rows) < previous_count:
        raise RuntimeError("Corpus shrank unexpectedly")
    ordered = sorted(rows.values(), key=lambda row: (row["posted_at"], row["channel_id"], row["message_id"]))
    payload = "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in ordered)
    return payload.encode("utf-8"), len(ordered)


def upload(bucket: str, data: bytes, generation: str) -> None:
    url = (f"https://storage.googleapis.com/upload/storage/v1/b/{quote(bucket, safe='')}/o"
           f"?uploadType=media&name={quote(OBJECT_NAME, safe='')}&ifGenerationMatch={generation}")
    result = json.loads(post(url, data, "application/x-ndjson; charset=utf-8", timeout=300))
    if result.get("name") != OBJECT_NAME or result.get("size") != str(len(data)):
        raise RuntimeError("Uploaded corpus size or name did not match")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--database", type=Path, default=ROOT / ".local" / "messages.sqlite3")
    args = parser.parse_args()
    try:
        previous, generation = existing_file(args.bucket)
        payload, count = merge_jsonl(previous, args.database)
        if payload != previous:
            upload(args.bucket, payload, generation)
        print(f"Training corpus: gs://{args.bucket}/{OBJECT_NAME}; {count} posts, {len(payload)} bytes")
    except (OSError, sqlite3.Error, ValueError, KeyError, RuntimeError) as error:
        parser.exit(1, f"Training export failed: {error}\n")


if __name__ == "__main__":
    main()
