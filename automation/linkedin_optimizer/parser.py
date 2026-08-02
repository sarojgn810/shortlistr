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
            # Same positional trap as the block path below: only treat the first
            # line as a name when it reads like one.
            if looks_like_person_name(lines[0]) and len(lines) > 1:
                profile["name"] = re.sub(r"[*_`]+", "", lines[0]).strip()[:80]
                lines = lines[1:]
            profile["headline"] = lines[0][:220]
            rest = lines[1:]
            for ln in rest[:4]:
                if looks_like_location(ln):
                    profile["location"] = re.sub(r"[*_`]+", "", ln).strip()
                    rest = [x for x in rest if x is not ln]
                    break
            profile["about"] = "\n".join(rest).strip()
        return profile

    preamble = []
    for key, body in blocks:
        if key is None:
            preamble.append(body)
            continue
        if key == "experience":
            profile["experience"] = _parse_experience(body)
        elif key == "skills":
            # Not "/": it is part of the skill, not a separator between two.
            # Splitting on it turned "CI/CD Integration" into "CI" and "CD
            # Integration", and "SLO / SLI / Error Budgets" into three.
            parts = re.split(r"[,•\n|]+", body)
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
            # Only take the first line as a name if it reads like one. A paste
            # that starts at the headline used to shift everything by one.
            rest = pre_lines
            if looks_like_person_name(pre_lines[0]):
                profile["name"] = re.sub(r"[*_`]+", "", pre_lines[0]).strip()[:80]
                rest = pre_lines[1:]
            if rest:
                profile["headline"] = rest[0][:220]
            # The line after the headline is often the location — but only if
            # it actually reads like one. Taking any short comma line put
            # "**Site Reliability Engineer" in the location field.
            for ln in rest[1:5]:
                if looks_like_location(ln):
                    profile["location"] = re.sub(r"[*_`]+", "", ln).strip()
                    break

    return profile


# Words that mean "this is a job title", not "this is where I live". A LinkedIn
# export puts the headline right where a location would be, and the old rule —
# any line under 60 chars containing a comma — happily took
# "**Site Reliability Engineer" as a location.
_ROLE_WORDS = (
    "engineer", "developer", "manager", "architect", "analyst", "consultant",
    "designer", "scientist", "director", "specialist", "administrator",
    "president", "founder", "head of", "intern", "freelance", "devops",
    "sre", "student", "professor", "teacher", "recruiter", "officer",
)


def looks_like_person_name(value: str) -> bool:
    """True when this reads like a person's name rather than a headline.

    The preamble used to be assigned positionally — first line name, second line
    headline. LinkedIn copy often starts at the headline instead (the name sits
    in an image or is skipped by the selection), and everything shifted by one:
    the headline landed in the name field and the real headline was lost.
    """
    s = re.sub(r"[*_`]+", "", str(value or "")).strip()
    if not (2 <= len(s) <= 60):
        return False
    low = s.lower()
    if any(ch in s for ch in "|@·•,/"):
        return False
    if any(ch.isdigit() for ch in s):
        return False
    if any(w in low for w in _ROLE_WORDS):
        return False
    words = s.split()
    if not (1 <= len(words) <= 4):
        return False
    return all(re.fullmatch(r"[A-Za-z][A-Za-z.'\-]*", w) for w in words)


def looks_like_location(value: str) -> bool:
    """True when this reads like a place rather than a headline or contact row.

    Locations are short, made of letters and separators, and name at most a
    city / region / country. Anything with a role word, a URL, an @, a headline
    separator, or a long run of digits is something else.
    """
    s = re.sub(r"[*_`]+", "", str(value or "")).strip().strip(",").strip()
    if not (2 <= len(s) <= 60):
        return False
    low = s.lower()
    if any(ch in s for ch in "|@·•"):
        return False
    if "http" in low or "www." in low:
        return False
    if re.search(r"\d{4,}", s):
        return False
    if any(w in low for w in _ROLE_WORDS):
        return False

    parts = [p.strip() for p in s.split(",") if p.strip()]
    if not (1 <= len(parts) <= 3):
        return False
    return all(
        2 <= len(p) <= 30 and re.fullmatch(r"[A-Za-z][A-Za-z .'\-()]*", p)
        for p in parts
    )


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
