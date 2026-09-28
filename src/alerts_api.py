"""Kyiv city air raid level from the alerts.in.ua active-alerts API."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from urllib.request import Request, urlopen

from src.formatting import display_time


ACTIVE_URL = "https://api.alerts.in.ua/v1/alerts/active.json"
KYIV_CITY_UID = "31"  # Kyiv Oblast is UID 14; it must not be used here.
VALID_STATES = {"clear", "yellow", "red", "active_unknown"}


def kyiv_air_raid_state(payload: object) -> tuple[str, str | None]:
    """Return city state and the matching alert as UTF-8 JSON, if present."""
    if not isinstance(payload, dict) or not isinstance(payload.get("alerts"), list):
        raise ValueError("Alerts API response has no alerts list")
    city_alerts = [
        alert for alert in payload["alerts"]
        if isinstance(alert, dict)
        and str(alert.get("location_uid")) == KYIV_CITY_UID
        and alert.get("alert_type") == "air_raid"
        and alert.get("finished_at") is None
    ]
    if not city_alerts:
        return "clear", None
    levels = {alert.get("alert_level") for alert in city_alerts}
    state = "red" if "red" in levels else "yellow" if "yellow" in levels else "active_unknown"
    return state, json.dumps(city_alerts, ensure_ascii=False, sort_keys=True)


def fetch_kyiv_air_raid_state(token: str) -> tuple[str, str | None]:
    request = Request(ACTIVE_URL, headers={"Authorization": f"Bearer {token}",
                                          "Accept": "application/json"})
    with urlopen(request, timeout=10) as response:
        payload = json.load(response)
    return kyiv_air_raid_state(payload)


def alert_status_message(state: str, checked_at: str) -> str:
    if state not in VALID_STATES:
        raise ValueError(f"Unknown Kyiv alert state: {state}")
    title = {
        "red": "🔴 <b>Київ · червоний рівень тривоги</b>",
        "yellow": "🟡 <b>Київ · жовтий рівень тривоги</b>",
        "clear": "🟢 <b>Київ · повітряної тривоги немає</b>",
        "active_unknown": "🚨 <b>Київ · тривога, рівень не вказано</b>",
    }[state]
    return f'{title}\n\n<a href="https://alerts.in.ua/">alerts.in.ua</a> · {display_time(checked_at)}'


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()
