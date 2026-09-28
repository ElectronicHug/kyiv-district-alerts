"""Read Telegram API credentials from environment or a local UTF-8 .env file."""

from __future__ import annotations

import os
import re
from pathlib import Path


HASH_PATTERN = re.compile(r"^[0-9a-fA-F]{32}$")


def read_local_env(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values = {}
    for number, raw_line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").strip()
        if "=" not in line:
            raise ValueError(f"Invalid .env line {number}")
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key not in {"TELEGRAM_API_ID", "TELEGRAM_API_HASH", "TELEGRAM_USE_IPV6", "ALERTS_API_TOKEN"}:
            continue
        values[key] = value
    return values


def load_credentials(project_root: Path) -> tuple[int, str]:
    local_values = read_local_env(project_root / ".env")
    api_id_text = os.environ.get("TELEGRAM_API_ID") or local_values.get("TELEGRAM_API_ID", "")
    api_hash = os.environ.get("TELEGRAM_API_HASH") or local_values.get("TELEGRAM_API_HASH", "")
    if not api_id_text.isdecimal() or not HASH_PATTERN.fullmatch(api_hash):
        raise ValueError("Set TELEGRAM_API_ID and TELEGRAM_API_HASH in the local .env file")
    return int(api_id_text), api_hash


def load_alerts_token(project_root: Path) -> str | None:
    token = os.environ.get("ALERTS_API_TOKEN") or read_local_env(project_root / ".env").get("ALERTS_API_TOKEN")
    return token.strip() if token and token.strip() else None


def load_telegram_ipv6(project_root: Path) -> bool:
    value = os.environ.get("TELEGRAM_USE_IPV6") or read_local_env(project_root / ".env").get("TELEGRAM_USE_IPV6", "0")
    if value not in {"0", "1"}:
        raise ValueError("TELEGRAM_USE_IPV6 must be 0 or 1")
    return value == "1"
