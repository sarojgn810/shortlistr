"""Parse pasted LinkedIn profile text into structured sections."""

from __future__ import annotations

import re
from typing import Any


_SECTION_HEADERS = {
    "about": re.compile(r"^(about|summary|overview)\s*$", re.I),
    "experience": re.compile(r"^(experience|work experience|employment)\s*$", re.I),
    "skills": re.compile(r"^(skills|top skills|expertise)\s*$", re.I),
    "featured": re.compile(r"^(featured|featured section)\s*$", re.I),
    "open_to_work": re.compile(r"^(open to work|open-to-work|preferences)\s*$", re.I),
    "contact": re.compile(r"^(contact|contact info|contact information)\s*$", re.I),
    "headline": re.compile(r"^(headline)\s*$", re.I),
}


def _split_blocks(text: str) -> list[tuple[str | None, str]]:
    lines = [ln.rstrip() for ln in (text or "").replace("\r\n", "\n").split("\n")]
    blocks: list[tuple[str | None, str]] = []
    current_key: str | None = None
    buf: list[str] = []

    def flush():
        nonlocal buf, current_key
        body = "\n".join(buf).strip()
        if body or current_key:
            blocks.append((current_key, body))
        buf = []

    for ln in lines:
        stripped = ln.strip()
        matched = None
        for key, pat in _SECTION_HEADERS.items():
            if pat.match(stripped):
                matched = key
                break
        if matched:
            flush()
            current_key = matched
            continue
        buf.append(ln)
    flush()
    return blocks


def _parse_experience(body: str) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    chunks = re.split(r"\n(?=[A-Z][^\n]{2,80}\n)", body.strip()) if body.strip() else []
    if not chunks and body.strip():
        chunks = [body]
    for chunk in chunks:
        lines = [ln.strip() for ln in chunk.split("\n") if ln.strip()]
        if not lines:
            continue
        title = lines[0]
        company = ""
        bullets: list[str] = []
        rest = lines[1:]
        if rest and not rest[0].startswith(("•", "-", "*")):
            company = rest[0]
            rest = rest[1:]
        for ln in rest:
            bullets.append(re.sub(r"^[\u2022\-\*\u2013]\s*", "", ln).strip())
        jobs.append({"title": title, "company": company, "bullets": [b for b in bullets if b]})
    return jobs


def parse_profile_text(text: str) -> dict[str, Any]:
    """Best-effort parse of freeform LinkedIn paste into sections."""
    text = (text or "").strip()
    profile: dict[str, Any] = {
        "raw": text,
        "name": "",
        "headline": "",
        "about": "",
        "experience": [],
        "skills": [],
        "featured": "",
        "open_to_work": "",
        "location": "",
        "contact": "",
    }
    if not text:
        return profile

    blocks = _split_blocks(text)
    # If no headers, treat first non-empty line as headline and rest as about.
    if len(blocks) == 1 and blocks[0][0] is None:
        lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
        if lines:
            profile["headline"] = lines[0][:220]
            profile["about"] = "\n".join(lines[1:]).strip()
        return profile

    preamble = []
    for key, body in blocks:
        if key is None:
            preamble.append(body)
            continue
        if key == "experience":
            profile["experience"] = _parse_experience(body)
        elif key == "skills":
            parts = re.split(r"[,•\n|/]+", body)
            profile["skills"] = [p.strip() for p in parts if p.strip()]
        elif key == "headline":
            profile["headline"] = body.strip()[:220]
        elif key == "about":
            profile["about"] = body.strip()
        elif key == "featured":
            profile["featured"] = body.strip()
        elif key == "open_to_work":
            profile["open_to_work"] = body.strip()
        elif key == "contact":
            profile["contact"] = body.strip()

    if preamble:
        pre_lines = [ln.strip() for ln in "\n".join(preamble).split("\n") if ln.strip()]
        if pre_lines and not profile["headline"]:
            profile["name"] = pre_lines[0][:80]
            if len(pre_lines) > 1:
                profile["headline"] = pre_lines[1][:220]
            # crude location: line containing city-like comma
            for ln in pre_lines[2:6]:
                if "," in ln and len(ln) < 60:
                    profile["location"] = ln
                    break

    return profile


def profile_from_structured(body: dict[str, Any]) -> dict[str, Any]:
    """Normalize a structured payload from the UI."""
    base = parse_profile_text("")
    for key in base:
        if key == "raw":
            continue
        if key in body and body[key] is not None:
            base[key] = body[key]
    for meta in ("linkedin_url", "source"):
        if body.get(meta):
            base[meta] = body[meta]
    if isinstance(base.get("skills"), str):
        base["skills"] = [s.strip() for s in re.split(r"[,•\n|/]+", base["skills"]) if s.strip()]
    if not isinstance(base.get("experience"), list):
        base["experience"] = []
    # Rebuild raw for scoring convenience
    parts = []
    if base.get("headline"):
        parts.append(base["headline"])
    if base.get("about"):
        parts += ["About", base["about"]]
    for job in base.get("experience") or []:
        parts.append(job.get("title") or "")
        parts.append(job.get("company") or "")
        parts.extend(job.get("bullets") or [])
    if base.get("skills"):
        parts += ["Skills", ", ".join(base["skills"])]
    base["raw"] = "\n".join(p for p in parts if p)
    return base
