"""Compact user identity for the chat agent (profile + CV snippets).

Injected into the system prompt so the assistant answers as *this* candidate,
not a generic bot. Never dumps the full CV — tools still own heavy work
(evaluate / prep / apply-assist).
"""

from __future__ import annotations

import os
import re


def _truncate(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", (text or "").strip())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _cv_highlights(limit: int = 900) -> str:
    try:
        import config

        path = getattr(config, "CV_MD_PATH", None) or os.path.join(
            getattr(config, "SHORTLISTR_ROOT", ""), "cv.md"
        )
        if not path or not os.path.isfile(path):
            return ""
        raw = open(path, encoding="utf-8", errors="ignore").read()
    except Exception:
        return ""
    # Prefer early sections (summary / skills) over the whole file.
    chunks: list[str] = []
    for block in re.split(r"\n#{1,3}\s+", raw):
        block = block.strip()
        if not block:
            continue
        chunks.append(block)
        if sum(len(c) for c in chunks) >= limit:
            break
    return _truncate(" | ".join(chunks), limit)


def profile_snapshot() -> dict:
    """Safe, serializable view of who the agent is helping."""
    try:
        import config

        cand = dict(getattr(config, "CANDIDATE", None) or {})
        filters = dict(getattr(config, "_FILTERS", None) or {})
        titles = list(filters.get("target_titles") or getattr(config, "SEARCH_KEYWORDS", None) or [])
        locations = list(getattr(config, "LOCATION_KEYWORDS", None) or [])
        # Prefer human-facing preferred_locations if present on the live profile.
        preferred = []
        try:
            preferred = list(config._preferred_locations())  # type: ignore[attr-defined]
        except Exception:
            preferred = []
        if preferred:
            locations = preferred
    except Exception:
        cand, titles, locations = {}, [], []

    return {
        "name": cand.get("name") or "",
        "email": cand.get("email") or "",
        "phone": cand.get("phone") or "",
        "location": cand.get("location") or "",
        "years_exp": cand.get("years_exp") or "",
        "linkedin": cand.get("linkedin") or "",
        "github": cand.get("github") or "",
        "target_titles": [str(t) for t in titles if t][:12],
        "target_locations": [str(loc) for loc in locations if loc][:8],
        "cv_highlights": _cv_highlights(),
        "has_cv": bool(_cv_highlights()),
    }


def context_block() -> str:
    """Markdown-ish block for the chat system prompt."""
    snap = profile_snapshot()
    if not any(snap.get(k) for k in ("name", "email", "target_titles", "cv_highlights")):
        return (
            "\nUser profile: not configured yet. If they ask who they are, "
            "tell them to finish onboarding / Profile in the dashboard."
        )

    lines = ["\nYou are helping THIS candidate (use these facts; do not invent others):"]
    if snap["name"]:
        lines.append(f"- Name: {snap['name']}")
    bits = []
    if snap["years_exp"]:
        bits.append(f"{snap['years_exp']} years exp")
    if snap["location"]:
        bits.append(str(snap["location"]))
    if bits:
        lines.append(f"- Background: {', '.join(bits)}")
    if snap["email"]:
        lines.append(f"- Email: {snap['email']}")
    if snap["linkedin"]:
        lines.append(f"- LinkedIn: {snap['linkedin']}")
    if snap["github"]:
        lines.append(f"- GitHub: {snap['github']}")
    if snap["target_titles"]:
        lines.append(f"- Target titles: {', '.join(snap['target_titles'])}")
    if snap["target_locations"]:
        lines.append(f"- Target locations: {', '.join(snap['target_locations'])}")
    if snap["cv_highlights"]:
        lines.append(f"- CV highlights: {snap['cv_highlights']}")
    lines.append(
        "- When they ask you to act (scan, evaluate, approve, skip, prep, prefill, email), "
        "call the matching tool. Never claim you submitted an application — they always click Submit."
    )
    return "\n".join(lines)
