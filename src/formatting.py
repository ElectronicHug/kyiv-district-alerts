"""Compact Telegram HTML messages with original-source links."""

from __future__ import annotations

from datetime import datetime
from html import escape
import re
from zoneinfo import ZoneInfo


KYIV = ZoneInfo("Europe/Kyiv")
MAX_HTML_LENGTH = 3500


def clean_source_text(text: str) -> str:
    """Remove standalone trailing channel signatures, preserving body mentions."""
    lines = text.rstrip().splitlines()
    while lines:
        if not lines[-1].strip():
            lines.pop()
        elif re.fullmatch(r"(?:@[A-Za-z][A-Za-z0-9_]{4,31}\s*)+", lines[-1].strip()):
            lines.pop()
        else:
            break
    return "\n".join(lines).strip()


def display_time(timestamp: str) -> str:
    value = datetime.fromisoformat(timestamp)
    if value.tzinfo is None:
        raise ValueError("Post timestamp must include a timezone")
    return value.astimezone(KYIV).strftime("%d.%m · %H:%M")


def escaped_parts(text: str, budget: int) -> list[str]:
    if budget < 16:
        raise ValueError("Telegram message header is too long")
    parts: list[str] = []
    current: list[str] = []
    used = 0
    for character in text:
        escaped = escape(character)
        if used + len(escaped) > budget and current:
            parts.append("".join(current))
            current = []
            used = 0
        current.append(escaped)
        used += len(escaped)
    if current:
        parts.append("".join(current))
    return parts


def message_chunks(
    channel: str, message_id: int, posted_at: str, text: str, edited_at: str | None = None,
    intro: str = "", context_message_id: int | None = None,
) -> list[str]:
    """Return HTML chunks; callers must send them with parse_mode='html'."""
    text = clean_source_text(text)
    if not text:
        return []
    source_url = f"https://t.me/{channel}/{message_id}"
    heading = f"<b>{escape(intro)}</b>" if intro else "<b>Повідомлення</b>"
    footer = (
        f'<a href="{source_url}">@{escape(channel)} ↗</a>'
        f" · {display_time(posted_at)}"
    )
    if edited_at:
        footer += f" · оновлено {display_time(edited_at)}"
    if context_message_id is not None:
        context_url = f"https://t.me/{channel}/{context_message_id}"
        footer += f' · <a href="{context_url}">Контекст ↗</a>'
    budget = MAX_HTML_LENGTH - len(heading) - len(footer) - 40
    parts = escaped_parts(text, budget)
    total = len(parts)
    return [
        f"{heading}{f' · {index}/{total}' if total > 1 else ''}\n\n"
        f"{part}\n\n{footer}"
        for index, part in enumerate(parts, start=1)
    ]


def digest_message(rows: list) -> str:
    """One quiet summary with linked excerpts."""
    lines = ["🗺️ <b>Київ та правий берег</b>"]
    for row in rows:
        excerpt = " ".join(clean_source_text(row["text"]).split())[:90]
        url = f"https://t.me/{row['channel_username']}/{row['message_id']}"
        lines.append(f'• <a href="{url}">{escape(excerpt)}</a>')
    result = lines[0] + "\n\n" + "\n".join(lines[1:])
    if len(result) > 4096:
        raise ValueError("Digest is too long for one Telegram message")
    return result
