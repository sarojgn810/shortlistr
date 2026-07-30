"""Import LinkedIn profile text from a public URL (best-effort) or paste.

LinkedIn almost always serves a login wall to anonymous scrapers. When that
happens we return an honest failure and the UI falls back to résumé / paste.
We never invent profile content from a URL that did not yield real text.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from linkedin_optimizer.parser import parse_profile_text

_LINKEDIN_IN_RE = re.compile(
    r"(?:https?://)?(?:www\.)?linkedin\.com/in/([A-Za-z0-9_-]+)/?",
    re.I,
)


def normalize_linkedin_url(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    m = _LINKEDIN_IN_RE.search(text)
    if m:
        return f"https://www.linkedin.com/in/{m.group(1)}"
    # Allow bare slug
    if re.fullmatch(r"[A-Za-z0-9_-]{3,100}", text):
        return f"https://www.linkedin.com/in/{text}"
    return ""


def _og_meta(html: str, prop: str) -> str:
    patterns = [
        rf'<meta[^>]+property=["\']{re.escape(prop)}["\'][^>]+content=["\']([^"\']+)["\']',
        rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']{re.escape(prop)}["\']',
    ]
    for pat in patterns:
        m = re.search(pat, html, re.I)
        if m:
            return re.sub(r"\s+", " ", m.group(1)).strip()
    return ""


def _looks_like_login_wall(html: str) -> bool:
    lower = (html or "").lower()
    markers = (
        "authwall",
        "join linkedin",
        "sign in",
        "session-redirect",
        "challenge",
        "checkpoint",
    )
    return any(m in lower for m in markers) and len(re.sub(r"<[^>]+>", " ", html)) < 2500


def fetch_public_profile(url: str) -> dict[str, Any]:
    """Try to read a public LinkedIn profile. Returns {ok, profile?, error?, url}."""
    normalized = normalize_linkedin_url(url)
    if not normalized:
        return {
            "ok": False,
            "url": url or "",
            "error": "Enter a LinkedIn profile URL like https://www.linkedin.com/in/your-handle",
            "profile": None,
        }

    html = ""
    via = ""
    try:
        # Prefer requests; Playwright often still hits the auth wall and is slower.
        from scrapers.browser_fetch import fetch_page

        page = fetch_page(normalized, ttl=0, allow_browser=False)
        html = page.html or ""
        via = page.via or "requests"
        if page.error and not html:
            return {
                "ok": False,
                "url": normalized,
                "error": f"Could not fetch profile ({page.error}). Paste your LinkedIn text or use your résumé.",
                "profile": None,
                "via": via,
            }
    except Exception as e:
        return {
            "ok": False,
            "url": normalized,
            "error": f"Fetch failed: {e}. Paste your LinkedIn text or import from résumé.",
            "profile": None,
        }

    if not html or _looks_like_login_wall(html):
        return {
            "ok": False,
            "url": normalized,
            "error": (
                "LinkedIn blocked anonymous access to this profile (login wall). "
                "Paste your profile text, or import from your résumé in AutoJob."
            ),
            "profile": None,
            "via": via,
        }

    title = _og_meta(html, "og:title")
    desc = _og_meta(html, "og:description")
    # Strip scripts/styles for a crude text dump
    text = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    # Prefer OG fields when body is thin
    if title or desc:
        lines = []
        if title:
            # "Name - Headline | LinkedIn"
            name_part = title.split("|")[0].strip()
            if " - " in name_part:
                name, headline = name_part.split(" - ", 1)
            else:
                name, headline = name_part, ""
            lines.append(name.strip())
            if headline:
                lines.append(headline.strip()[:220])
        if desc:
            lines += ["About", desc]
        seed = "\n".join(lines)
    else:
        seed = text[:8000]

    if len(seed) < 40:
        return {
            "ok": False,
            "url": normalized,
            "error": "Profile page returned almost no readable text. Paste your LinkedIn sections instead.",
            "profile": None,
            "via": via,
        }

    profile = parse_profile_text(seed)
    profile["linkedin_url"] = normalized
    profile["source"] = "linkedin"
    return {
        "ok": True,
        "url": normalized,
        "profile": profile,
        "via": via,
        "error": "",
        "partial": not bool(profile.get("experience")),
        "hint": (
            "Public pages often only expose name/headline/about. "
            "Paste Experience & Skills from LinkedIn for a full score, or import from résumé."
            if not profile.get("experience")
            else ""
        ),
    }
