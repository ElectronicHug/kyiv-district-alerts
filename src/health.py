"""Local heartbeat for checking whether the relay loop is making progress."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def write_heartbeat(path: Path, channels: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "sources": channels,
    }
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def check_heartbeat(path: Path, max_age_seconds: int, *, now: datetime | None = None) -> tuple[bool, str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        updated_at = datetime.fromisoformat(payload["updated_at"])
        if updated_at.tzinfo is None:
            raise ValueError("timestamp has no timezone")
    except (OSError, ValueError, KeyError, TypeError) as error:
        return False, f"Heartbeat unavailable: {error}"
    current = now or datetime.now(timezone.utc)
    age = (current - updated_at).total_seconds()
    if age < -30:
        return False, "Heartbeat timestamp is in the future"
    if age > max_age_seconds:
        return False, f"Heartbeat is stale ({age:.0f}s)"
    return True, f"Relay loop active; heartbeat age {age:.0f}s"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", type=Path, default=ROOT / ".local" / "heartbeat.json")
    parser.add_argument("--max-age-seconds", type=int, default=120)
    args = parser.parse_args()
    if args.max_age_seconds < 1:
        parser.error("--max-age-seconds must be positive")
    healthy, message = check_heartbeat(args.path, args.max_age_seconds)
    print(message)
    if not healthy:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
