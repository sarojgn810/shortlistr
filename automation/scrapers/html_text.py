"""HTML → compact markdown for job pages.

Mines structured blobs from inline scripts (e.g. Next.js page props) before
stripping chrome, so SPA careers pages keep their job payload without a full
browser render when the data is already in the HTML.
"""

from __future__ import annotations

import html
import json
import re
from typing import Any

# Kept for callers that imported the old name.
__all__ = ["html_to_plain", "html_to_markdown", "mine_script_json"]

_SCRIPT_RE = re.compile(r"<script\b[^>]*>(.*?)</script>", re.I | re.S)
_STYLE_RE = re.compile(r"<style\b[^>]*>.*?</style>", re.I | re.S)
_BODY_RE = re.compile(r"<body\b[^>]*>(.*?)</body>", re.I | re.S)
_NEXT_DATA_RE = re.compile(
    r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
    re.I | re.S,
)
_ASSIGN_RE = re.compile(
    r"(?:window\.)?(__NEXT_DATA__|__INITIAL_STATE__|__PRELOADED_STATE__|"
    r"jobPosting|jobDetails|jobData)\s*=\s*(\{.*?\})\s*;?\s*(?:</script>|$)",
    re.I | re.S,
)


def mine_script_json(raw_html: str) -> list[Any]:
    """Pull JSON objects out of inline script tags and known SSR markers."""
    found: list[Any] = []
    if not raw_html:
        return found

    for m in _NEXT_DATA_RE.finditer(raw_html):
        blob = (m.group(1) or "").strip()
        parsed = _try_json(blob)
        if parsed is not None:
            found.append(parsed)

    for m in _SCRIPT_RE.finditer(raw_html):
        body = (m.group(1) or "").strip()
        if not body or "application/ld+json" in (m.group(0) or "").lower():
            # ld+json is handled below via full-tag attribute scan
            pass
        if body.startswith("{") or body.startswith("["):
            parsed = _try_json(body)
            if parsed is not None:
                found.append(parsed)
                continue
        for am in _ASSIGN_RE.finditer(body):
            parsed = _try_json(am.group(2))
            if parsed is not None:
                found.append(parsed)

    for m in re.finditer(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        raw_html,
        re.I | re.S,
    ):
        parsed = _try_json((m.group(1) or "").strip())
        if parsed is not None:
            found.append(parsed)

    return found


def _try_json(text: str) -> Any | None:
    if not text:
        return None
    try:
        return json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None


def _flatten_json(value: Any, *, depth: int = 0) -> list[str]:
    """Turn nested JSON into short prose lines (keys that look like job fields)."""
    if depth > 6 or value is None:
        return []
    lines: list[str] = []
    interesting = {
        "title",
        "name",
        "role",
        "location",
        "locations",
        "description",
        "jobdescription",
        "requirements",
        "responsibilities",
        "department",
        "team",
        "company",
        "employmenttype",
        "salary",
        "headline",
    }
    if isinstance(value, dict):
        for key, child in value.items():
            key_l = str(key).lower().replace("_", "").replace("-", "")
            if key_l in interesting and isinstance(child, str) and child.strip():
                label = str(key).replace("_", " ").strip().title()
                text = re.sub(r"\s+", " ", child.strip())
                if len(text) > 20 or key_l in {"title", "name", "location", "company"}:
                    lines.append(f"**{label}:** {text[:2000]}")
            else:
                lines.extend(_flatten_json(child, depth=depth + 1))
    elif isinstance(value, list):
        for item in value[:40]:
            lines.extend(_flatten_json(item, depth=depth + 1))
    elif isinstance(value, str) and len(value.strip()) > 80:
        # Long free-text leaves often are JD fragments.
        lines.append(re.sub(r"\s+", " ", value.strip())[:2000])
    return lines


def html_to_markdown(raw_html: str, *, max_len: int = 12000, base_url: str = "") -> str:
    """Compress a page into markdown-ish text suitable for scoring / local LLM."""
    if not raw_html or not str(raw_html).strip():
        return ""

    mined_lines: list[str] = []
    for blob in mine_script_json(raw_html):
        mined_lines.extend(_flatten_json(blob))

    title = ""
    tm = re.search(r"<title[^>]*>(.*?)</title>", raw_html, re.I | re.S)
    if tm:
        title = re.sub(r"\s+", " ", html.unescape(tm.group(1))).strip()

    body_m = _BODY_RE.search(raw_html)
    body = body_m.group(1) if body_m else raw_html
    body = _STYLE_RE.sub("", body)
    body = _SCRIPT_RE.sub("", body)

    links: list[str] = []
    for hm in re.finditer(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', body, re.I | re.S):
        href, label = hm.group(1), re.sub(r"<[^>]+>", "", hm.group(2))
        label = re.sub(r"\s+", " ", html.unescape(label)).strip()
        if href.startswith("http") and label:
            links.append(f"- [{label[:80]}]({href})")

    text = body
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</p>", "\n\n", text, flags=re.I)
    text = re.sub(r"</h[1-6]>", "\n\n", text, flags=re.I)
    text = re.sub(r"<h([1-6])[^>]*>", r"\n\n### ", text, flags=re.I)
    text = re.sub(r"<li[^>]*>", "\n- ", text, flags=re.I)
    text = re.sub(r"</(div|section|article|tr)>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    parts: list[str] = []
    if title:
        parts.append(f"# {title}")
    if mined_lines:
        # Prefer mined structured fields — they are the token-saving win.
        parts.append("\n".join(list(dict.fromkeys(mined_lines))[:80]))
    if text:
        parts.append(text)
    if links:
        parts.append("## Links\n" + "\n".join(list(dict.fromkeys(links))[:30]))

    out = "\n\n".join(p for p in parts if p).strip()
    if max_len and len(out) > max_len:
        return out[:max_len]
    return out


def html_to_plain(text: str, *, max_len: int = 8000) -> str:
    """Backward-compatible plain extract; uses markdown compressor when HTML-ish."""
    if not text or not str(text).strip():
        return ""
    raw = str(text)
    if "<" in raw and ">" in raw:
        md = html_to_markdown(raw, max_len=max_len)
        # Collapse markdown emphasis for callers that want plain text.
        plain = re.sub(r"[#*_`\[\]]+", "", md)
        plain = re.sub(r"\n{3,}", "\n\n", plain).strip()
        return plain[:max_len] if max_len else plain
    plain = html.unescape(raw)
    plain = re.sub(r"\s+", " ", plain).strip()
    return plain[:max_len] if max_len and len(plain) > max_len else plain
