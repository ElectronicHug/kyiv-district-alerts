"""Publish a metric only while the local relay heartbeat is fresh."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from scripts.gcp_common import post, project_id
from src.health import check_heartbeat


ROOT = Path(__file__).resolve().parents[1]
METRIC = "custom.googleapis.com/air_notification/heartbeat"


def publish(project: str) -> None:
    timestamp = datetime.now(timezone.utc).isoformat()
    body = {"timeSeries": [{
        "metric": {"type": METRIC},
        "resource": {"type": "global", "labels": {"project_id": project}},
        "points": [{"interval": {"endTime": timestamp}, "value": {"int64Value": "1"}}],
    }]}
    post(f"https://monitoring.googleapis.com/v3/projects/{project}/timeSeries",
         json.dumps(body).encode("utf-8"), "application/json")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--heartbeat", type=Path, default=ROOT / ".local" / "heartbeat.json")
    parser.add_argument("--max-age-seconds", type=int, default=120)
    args = parser.parse_args()
    healthy, message = check_heartbeat(args.heartbeat, args.max_age_seconds)
    if not healthy:
        parser.exit(1, f"No metric published: {message}\n")
    publish(project_id())
    print(f"Published relay heartbeat: {message}")


if __name__ == "__main__":
    main()
