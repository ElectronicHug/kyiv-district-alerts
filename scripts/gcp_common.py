"""Small standard-library helpers for authenticated Google Cloud REST calls."""

from __future__ import annotations

import json
from urllib.request import Request, urlopen


METADATA = "http://metadata.google.internal/computeMetadata/v1"


def metadata(path: str) -> str:
    request = Request(f"{METADATA}/{path}", headers={"Metadata-Flavor": "Google"})
    with urlopen(request, timeout=15) as response:
        return response.read().decode("utf-8")


def access_token() -> str:
    return json.loads(metadata("instance/service-accounts/default/token"))["access_token"]


def project_id() -> str:
    return metadata("project/project-id")


def post(url: str, body: bytes, content_type: str, *, timeout: int = 60) -> bytes:
    request = Request(url, data=body, method="POST", headers={
        "Authorization": f"Bearer {access_token()}",
        "Content-Type": content_type,
    })
    with urlopen(request, timeout=timeout) as response:
        return response.read()
