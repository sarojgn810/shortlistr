"""Minimal Apify REST client — no apify-client package required.

Opt-in only. Token from secrets_store / APIFY_TOKEN. Actors run on Apify's
cloud (same pattern as SerpAPI): the user's key, never a product default.
"""

from __future__ import annotations

import logging
import time
from typing import Any
from urllib.parse import quote

import requests

logger = logging.getLogger(__name__)

APIFY_API = "https://api.apify.com/v2"


def _actor_path(actor_id: str) -> str:
    # Apify accepts "user/actor" in the UI; the REST path wants "user~actor".
    return quote(actor_id.replace("/", "~"), safe="~")


def get_apify_token() -> str:
    try:
        from secrets_store import get_secret

        return (get_secret("APIFY_TOKEN") or "").strip()
    except Exception:
        import os

        return (os.environ.get("APIFY_TOKEN") or "").strip()


def run_actor(
    actor_id: str,
    run_input: dict[str, Any],
    *,
    token: str | None = None,
    timeout_secs: int = 180,
    poll_secs: float = 3.0,
) -> list[dict[str, Any]]:
    """Start an actor, wait for SUCCEEDED, return dataset items.

    Raises RuntimeError on missing token, HTTP failure, or non-success status.
    """
    tok = (token if token is not None else get_apify_token()).strip()
    if not tok:
        raise RuntimeError("APIFY_TOKEN not set")

    headers = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
    start = requests.post(
        f"{APIFY_API}/acts/{_actor_path(actor_id)}/runs",
        params={"waitForFinish": 0},
        json=run_input,
        headers=headers,
        timeout=30,
    )
    if start.status_code >= 400:
        raise RuntimeError(f"Apify start {actor_id}: HTTP {start.status_code} {start.text[:200]}")
    run = (start.json() or {}).get("data") or {}
    run_id = run.get("id")
    if not run_id:
        raise RuntimeError(f"Apify start {actor_id}: no run id in {start.text[:200]}")

    deadline = time.monotonic() + max(30, timeout_secs)
    status = run.get("status") or "RUNNING"
    while status in ("READY", "RUNNING", "TIMING-OUT") and time.monotonic() < deadline:
        time.sleep(poll_secs)
        poll = requests.get(
            f"{APIFY_API}/actor-runs/{run_id}",
            headers=headers,
            timeout=30,
        )
        if poll.status_code >= 400:
            raise RuntimeError(f"Apify poll {run_id}: HTTP {poll.status_code}")
        run = (poll.json() or {}).get("data") or {}
        status = run.get("status") or "FAILED"

    if status != "SUCCEEDED":
        raise RuntimeError(f"Apify run {actor_id} ended {status}")

    dataset_id = run.get("defaultDatasetId")
    if not dataset_id:
        return []

    items = requests.get(
        f"{APIFY_API}/datasets/{dataset_id}/items",
        params={"format": "json", "clean": 1},
        headers=headers,
        timeout=60,
    )
    if items.status_code >= 400:
        raise RuntimeError(f"Apify dataset {dataset_id}: HTTP {items.status_code}")
    data = items.json()
    return data if isinstance(data, list) else []
