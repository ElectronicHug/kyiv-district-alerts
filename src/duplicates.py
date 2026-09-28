"""Conservative cross-channel suppression for brief repeated area reports."""

from __future__ import annotations

import re

from src.formatting import clean_source_text
from src.relevance import Decision, RelevanceRules, normalize


def threat_type(text: str) -> str:
    value = normalize(text)
    if re.search(r"\b(?:ракет\w*|баліст\w*|крилат\w*)\b", value) or "🚀" in text:
        return "missile"
    if re.search(r"\b(?:реактив\w*)\b", value):
        return "jet_drone"
    if re.search(r"\b(?:шахед\w*|бпла|дрон\w*)\b", value) or "🛵" in text:
        return "drone"
    return "unspecified"


def repeated_report(text: str, decision: Decision, previous_text: str, previous: Decision,
                    rules: RelevanceRules) -> bool:
    current = normalize(clean_source_text(text))
    old = normalize(clean_source_text(previous_text))
    if not current or decision.is_clear != previous.is_clear:
        return False
    if not set(decision.places).intersection(previous.places):
        return False
    current_type, old_type = threat_type(text), threat_type(previous_text)
    if current_type != old_type and not {current_type, old_type} <= {"unspecified", "drone"}:
        return False
    if current == old:
        return True
    # Keep quantities, explicit new threats, detailed routes and long updates.
    if max(len(current), len(old)) > 100 or re.search(r"\d", current + old):
        return False
    if re.search(r"\b(?:ще|нов\w*|друг\w*|повтор\w*)\b", current + " " + old):
        return False
    # Only a small status vocabulary is eligible; extra locations/details survive.
    residuals = []
    for value in (current, old):
        for groups in rules.places.values():
            for place, aliases in groups.items():
                if place in set(decision.places + previous.places):
                    for alias in sorted(aliases, key=len, reverse=True):
                        value = re.sub(rf"(?<!\w){re.escape(normalize(alias))}(?!\w)", " ", value)
        residuals.append(value)
    allowed = r"(?:київ|києві|києва|зниження|падає|падіння|увага|шахед\w*|бпла|дрон\w*|чисто|відбій)"
    return all(not re.sub(rf"\b{allowed}\b", " ", value).strip() for value in residuals)
