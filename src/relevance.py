"""Conservative, explainable geography rules for offline post review."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import yaml


TIERS = ("direct", "nearby", "broad")


def normalize(text: str) -> str:
    text = text.casefold().replace("’", "'").replace("ʼ", "'").replace("`", "'")
    text = text.replace("'", "")
    return re.sub(r"[^\w]+", " ", text, flags=re.UNICODE).strip()


def contains_phrase(normalized_text: str, phrase: str) -> bool:
    normalized_phrase = normalize(phrase)
    if not normalized_phrase:
        return False
    return re.search(rf"(?<!\w){re.escape(normalized_phrase)}(?!\w)", normalized_text) is not None


def warning_after_clear(text: str) -> bool:
    """Detect a new threat stated after a separate all-clear sentence."""
    clear = re.search(r"(?<!\w)(?:чисто|відбій)(?!\w)", text.casefold())
    if clear is None:
        return False
    remainder = text[clear.end():]
    boundary = re.search(r"[.!?\n]", remainder)
    if boundary is None:
        return False
    later = normalize(remainder[boundary.end():])
    return re.search(r"(?<!\w)(?:шахед\w*|реактив\w*|бпла|ракета\w*|ракетн\w*)(?!\w)", later) is not None


@dataclass(frozen=True)
class Decision:
    action: str
    tier: str | None
    places: tuple[str, ...]
    reason: str
    is_clear: bool = False
    context_message_id: int | None = None


class RelevanceRules:
    def __init__(self, places: dict[str, dict[str, list[str]]], clear_phrases: list[str],
                 status_phrases: list[str], distant_places: list[str],
                 max_broad_text_length: int, reply_context_hours: int):
        self.places = places
        self.clear_phrases = clear_phrases
        self.status_phrases = status_phrases
        self.distant_places = distant_places
        self.max_broad_text_length = max_broad_text_length
        self.reply_context_hours = reply_context_hours

    @classmethod
    def from_yaml(cls, path: Path) -> "RelevanceRules":
        with path.open("r", encoding="utf-8") as file:
            config = yaml.safe_load(file)
        relevance = config.get("relevance") if isinstance(config, dict) else None
        if not isinstance(relevance, dict):
            raise ValueError("config.yaml needs a relevance section")
        places = {}
        for tier in TIERS:
            groups = relevance.get(tier)
            if not isinstance(groups, dict) or not groups:
                raise ValueError(f"relevance.{tier} must contain named places")
            places[tier] = {}
            for name, aliases in groups.items():
                if not isinstance(name, str) or not isinstance(aliases, list) or not aliases:
                    raise ValueError(f"Invalid aliases in relevance.{tier}")
                if any(not isinstance(alias, str) or not normalize(alias) for alias in aliases):
                    raise ValueError(f"Invalid alias for {name}")
                places[tier][name] = aliases
        clear_phrases = relevance.get("clear_phrases")
        if not isinstance(clear_phrases, list) or any(
            not isinstance(phrase, str) or not normalize(phrase) for phrase in clear_phrases
        ):
            raise ValueError("relevance.clear_phrases must be a list of phrases")
        status_phrases = relevance.get("status_phrases")
        if not isinstance(status_phrases, list) or any(
            not isinstance(phrase, str) or not normalize(phrase) for phrase in status_phrases
        ):
            raise ValueError("relevance.status_phrases must be a list of phrases")
        distant_places = relevance.get("distant_places")
        if not isinstance(distant_places, list) or any(
            not isinstance(phrase, str) or not normalize(phrase) for phrase in distant_places
        ):
            raise ValueError("relevance.distant_places must be a list of phrases")
        max_broad_text_length = relevance.get("max_broad_text_length")
        if (not isinstance(max_broad_text_length, int) or isinstance(max_broad_text_length, bool)
                or max_broad_text_length < 1):
            raise ValueError("relevance.max_broad_text_length must be a positive integer")
        reply_context_hours = relevance.get("reply_context_hours")
        if (not isinstance(reply_context_hours, int) or isinstance(reply_context_hours, bool)
                or reply_context_hours < 1):
            raise ValueError("relevance.reply_context_hours must be a positive integer")
        return cls(places, clear_phrases, status_phrases, distant_places,
                   max_broad_text_length, reply_context_hours)

    def classify(self, text: str) -> Decision:
        normalized = normalize(text)
        if not normalized:
            return Decision("skip", None, (), "Немає тексту")
        clear = any(contains_phrase(normalized, phrase) for phrase in self.clear_phrases)
        status = any(contains_phrase(normalized, phrase) for phrase in self.status_phrases)
        mixed_clear = clear and warning_after_clear(text)
        matches = {
            tier: tuple(
                name for name, aliases in self.places[tier].items()
                if any(contains_phrase(normalized, alias) for alias in aliases)
            )
            for tier in TIERS
        }
        if "Центр" in matches["direct"] and re.search(r"\b(?:центр\w* лів\w*|лів\w* центр\w*)\b", normalized):
            matches["direct"] = tuple(place for place in matches["direct"] if place != "Центр")
        for tier in TIERS:
            if matches[tier]:
                places = matches[tier]
                if tier == "broad" and "Правий берег" not in places and any(
                    contains_phrase(normalized, phrase) for phrase in self.distant_places
                ):
                    return Decision("skip", tier, places, "Згадано Київ, але місце на лівому березі", clear)
                if tier == "broad" and len(text) > self.max_broad_text_length:
                    return Decision("skip", tier, places, "Довгий загальний допис без близького місця", clear)
                if mixed_clear:
                    action = "notify"
                    reason = f"Змішаний допис: «чисто» та нова загроза; згадано: {', '.join(places)}"
                elif clear:
                    action = "notify"
                    reason = f"Повідомлення про «чисто»/відбій для: {', '.join(places)}"
                elif status:
                    action = "digest" if tier != "broad" else "skip"
                    reason = f"Службовий статус; згадано: {', '.join(places)}"
                else:
                    action = "notify" if tier != "broad" else "digest"
                    reason = f"Пряма згадка місця: {', '.join(places)}"
                return Decision(action, tier, places, reason, clear and not mixed_clear)
        return Decision("skip", None, (), "Немає підтвердженої згадки цільової зони", clear and not mixed_clear)

    def classify_with_reply(self, text: str, posted_at: str, parent: dict | None) -> Decision:
        decision = self.classify(text)
        if decision.tier is not None or not decision.is_clear or parent is None:
            return decision
        try:
            age = datetime.fromisoformat(posted_at) - datetime.fromisoformat(parent["posted_at"])
        except (KeyError, TypeError, ValueError):
            return decision
        if not timedelta(0) <= age <= timedelta(hours=self.reply_context_hours):
            return decision
        parent_decision = self.classify(parent["text"])
        if parent_decision.tier not in ("direct", "nearby"):
            return decision
        places = parent_decision.places
        return Decision(
            "notify", parent_decision.tier, places,
            f"«Чисто» у відповіді на допис про: {', '.join(places)}",
            True, parent["message_id"],
        )
