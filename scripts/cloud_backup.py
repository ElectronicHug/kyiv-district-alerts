"""Upload a consistent, private relay backup to Google Cloud Storage."""

from __future__ import annotations

import argparse
import io
import json
import sqlite3
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from scripts.backup_database import backup_database
from scripts.gcp_common import post


ROOT = Path(__file__).resolve().parents[1]


def make_archive(data_dir: Path) -> bytes:
    with tempfile.TemporaryDirectory() as directory:
        copies = Path(directory)
        for name in ("messages.sqlite3", "telegram.session"):
            backup_database(data_dir / name, copies / name)
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
            for name in ("messages.sqlite3", "telegram.session"):
                archive.add(copies / name, arcname=name, recursive=False)
        return buffer.getvalue()


def upload(bucket: str, object_name: str, data: bytes) -> None:
    url = (f"https://storage.googleapis.com/upload/storage/v1/b/{quote(bucket, safe='')}/o"
           f"?uploadType=media&name={quote(object_name, safe='')}&ifGenerationMatch=0")
    response = json.loads(post(url, data, "application/gzip"))
    if response.get("name") != object_name or response.get("size") != str(len(data)):
        raise RuntimeError("Storage upload response did not match the backup")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--data-dir", type=Path, default=ROOT / ".local")
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    object_name = f"relay/air-notification-{stamp}.tar.gz"
    try:
        data = make_archive(args.data_dir)
        upload(args.bucket, object_name, data)
    except (OSError, sqlite3.Error, RuntimeError, KeyError) as error:
        parser.exit(1, f"Cloud backup failed: {error}\n")
    print(f"Cloud backup verified: gs://{args.bucket}/{object_name} ({len(data)} bytes)")


if __name__ == "__main__":
    main()
