"""Optional page-reader boost for careers / JD fetching.

When enabled (Connections or SHORTLISTR_PAGE_READER=1), empty SPA shells and hard
HTTP blocks are retried via an external markdown reader before Playwright.
No third-party CLI is installed or required.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import requests

logger = logging.getLogger(__name__)

# Implementation detail — not shown as a product brand in the UI.
_READER_PREFIX = "https://r.jina.ai/"
_READER_HEADERS = {
    "User-Agent": "Shortlistr/1.0 (+local; optional page-reader boost)",
    "Accept": "text/plain, text/markdown, */*",
}


def is_enabled() -> bool:
    """True when the user opted in via Connections / profile / env."""
    env = (os.environ.get("SHORTLISTR_PAGE_READER") or "").strip().lower()
    if env in ("1", "true", "yes", "on"):
        return True
    if env in ("0", "false", "no", "off"):
        return False
    # Legacy env from the short-lived Agent Reach experiment.
    legacy = (os.environ.get("SHORTLISTR_AGENT_REACH") or "").strip().lower()
    if legacy in ("1", "true", "yes", "on"):
        return True
    if legacy in ("0", "false", "no", "off"):
        return False
    try:
        from paths import PROFILE_PATH
        import yaml

        if not os.path.isfile(PROFILE_PATH):
            return False
        with open(PROFILE_PATH, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if not isinstance(data, dict):
            return False
        sources = data.get("sources") if isinstance(data.get("sources"), dict) else {}
        pr = sources.get("page_reader") if isinstance(sources.get("page_reader"), dict) else {}
        if "enabled" in pr:
            return bool(pr.get("enabled"))
        # Migrate read: earlier builds stored sources.agent_reach.enabled
        ar = sources.get("agent_reach") if isinstance(sources.get("agent_reach"), dict) else {}
        return bool(ar.get("enabled"))
    except Exception:
        return False


def status_for_ui() -> dict[str, Any]:
    enabled = is_enabled()
    return {
        "enabled": enabled,
        "ready": enabled,
        "hint": (
            "Page fetch uses an external reader when HTTP returns an empty shell."
            if enabled
            else "Turn on to recover empty careers / JD pages before Playwright."
        ),
    }


def fetch_via_reader(url: str, *, timeout: int = 25) -> tuple[str, str]:
    """Return (markdown_or_text, error). Empty text means failure."""
    target = (url or "").strip()
    if not target.startswith(("http://", "https://")):
        return "", "invalid url"
    if target.startswith(_READER_PREFIX):
        reader_url = target
    else:
        reader_url = _READER_PREFIX + target
    try:
        resp = requests.get(reader_url, headers=_READER_HEADERS, timeout=timeout)
        text = (resp.text or "").strip()
        if resp.status_code >= 400:
            return "", f"reader HTTP {resp.status_code}"
        if len(text) < 80:
            return "", "reader returned empty body"
        return text, ""
    except Exception as exc:
        return "", str(exc)[:240]


def markdown_as_html(md: str) -> str:
    """Wrap reader markdown so existing HTML→text pipelines still work."""
    import html as html_lib

    safe = html_lib.escape(md or "")
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        "<title>Page reader</title></head><body>"
        f'<article class="page-reader"><pre>{safe}</pre></article>'
        "</body></html>"
    )
