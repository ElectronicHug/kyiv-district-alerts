"""Create a consistent SQLite backup without stopping the relay."""

from __future__ import annotations

import argparse
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def backup_database(source_path: Path, destination_path: Path) -> None:
    if source_path.resolve() == destination_path.resolve():
        raise ValueError("Backup destination must differ from the live database")
    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    if destination_path.exists():
        raise FileExistsError(destination_path)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    source_uri = source_path.resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(source_uri, uri=True)) as source:
        with closing(sqlite3.connect(destination_path)) as destination:
            source.backup(destination)
            result = destination.execute("PRAGMA integrity_check").fetchone()[0]
            if result != "ok":
                raise sqlite3.DatabaseError(f"Backup integrity check failed: {result}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=ROOT / ".local" / "messages.sqlite3")
    default_name = "messages-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".sqlite3"
    parser.add_argument("--output", type=Path, default=ROOT / ".local" / "backups" / default_name)
    args = parser.parse_args()
    try:
        backup_database(args.database, args.output)
    except (OSError, sqlite3.Error, ValueError) as error:
        parser.exit(1, f"Backup failed: {error}\n")
    print(f"Backup verified: {args.output}")


if __name__ == "__main__":
    main()
