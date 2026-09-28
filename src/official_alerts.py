"""Recognize explicit Kyiv air alert levels in the official KMVA channel."""

from __future__ import annotations

import re


_YELLOW = re.compile(r"^🟡\s*жовтий рівень небезпеки\b", re.IGNORECASE)
_RED = re.compile(r"^🔴\s*червоний рівень небезпеки\b", re.IGNORECASE)
_CLEAR = re.compile(
    r"^🟢\s*(?:м\.\s*київ\s*[-–—]\s*)?відбій повітряної тривоги\b",
    re.IGNORECASE,
)


def official_kyiv_alert_state(text: str) -> str | None:
    """Only explicit state headlines count; unrelated KMVA posts return None."""
    headline = next((line.strip() for line in text.splitlines() if line.strip()), "")
    if _YELLOW.match(headline):
        return "yellow"
    if _RED.match(headline):
        return "red"
    if _CLEAR.match(headline):
        return "clear"
    return None


def official_kyiv_alert_intro(state: str) -> str:
    return {
        "yellow": "🟡 Київ · жовтий рівень тривоги",
        "red": "🔴 Київ · червоний рівень тривоги",
        "clear": "🟢 Київ · відбій повітряної тривоги",
    }[state]
