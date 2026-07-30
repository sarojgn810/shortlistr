"""Parse cv.md into ATS-friendly sections."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_HEADING = re.compile(r"^#{1,2}\s+(.+)$", re.M)
_BULLET = re.compile(r"^[-*•]\s+", re.M)

_SECTION_HEADINGS = frozenset(
    {
        "professional summary",
        "summary",
        "profile",
        "about",
        "core competencies",
        "skills",
        "technical skills",
        "core skills",
        "professional experience",
        "experience",
        "work experience",
        "education",
        "certifications",
        "certificates",
        "key achievements",
        "achievements",
        "highlights",
        "projects",
        "resume",
        "cv",
        "curriculum vitae",
    }
)

_GENERIC_NAMES = frozenset({"resume", "cv", "curriculum vitae", "your name"})


@dataclass
class CvSections:
    name: str = ""
    contact: str = ""
    summary: str = ""
    skills: str = ""
    experience: str = ""
    education: str = ""
    certifications: str = ""
    projects: str = ""
    achievements: str = ""
    extra: dict[str, str] = field(default_factory=dict)


def _norm_heading(h: str) -> str:
    return re.sub(r"\s+", " ", h.strip().lower())


def _looks_like_person_name(text: str) -> bool:
    t = text.strip()
    if not t or len(t) < 3 or len(t) > 60:
        return False
    low = t.lower()
    if low in _GENERIC_NAMES:
        return False
    if _norm_heading(t) in _SECTION_HEADINGS:
        return False
    if "@" in t or re.search(r"https?://", t, re.I):
        return False
    if re.search(r"\d{3,}", t):
        return False
    # Mostly letters/spaces/punctuation common in names
    letters = sum(1 for c in t if c.isalpha())
    return letters >= max(3, len(t) // 3)


def infer_cv_name(md: str, sections: CvSections | None = None) -> str:
    """Best-effort candidate name from markdown."""
    sections = sections or parse_cv_markdown(md)
    if _looks_like_person_name(sections.name):
        return sections.name.strip()

    for m in re.finditer(r"^#\s+(.+)$", md, re.M):
        candidate = m.group(1).strip()
        if _looks_like_person_name(candidate):
            return candidate

    for line in md.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("**") and s.endswith("**"):
            continue
        if _looks_like_person_name(s):
            return s
        # First non-heading line that isn't contact — stop after one try
        if "@" not in s and not re.search(r"\+?\d[\d\s\-()]{8,}", s):
            break

    return sections.name.strip()


def parse_cv_markdown(md: str) -> CvSections:
    sections = CvSections()
    if not md or not md.strip():
        return sections

    lines = md.strip().splitlines()
    if lines and lines[0].startswith("# "):
        sections.name = lines[0][2:].strip()
        md_body = "\n".join(lines[1:])
    else:
        md_body = md

    parts: dict[str, list[str]] = {}
    current = "__preamble__"
    parts[current] = []

    for line in md_body.splitlines():
        m = re.match(r"^#{1,2}\s+(.+)$", line)
        if m:
            current = _norm_heading(m.group(1))
            parts.setdefault(current, [])
        else:
            parts.setdefault(current, []).append(line)

    preamble = "\n".join(parts.pop("__preamble__", [])).strip()
    if preamble and not sections.contact:
        sections.contact = preamble

    for key, body_lines in parts.items():
        body = "\n".join(body_lines).strip()
        if not body:
            continue
        # Exact names first, then tolerant contains-matching for real-world
        # compound headings ("TECHNICAL SKILLS & CORE COMPETENCIES",
        # "Professional Experience & Achievements", …).
        if key in ("professional summary", "summary", "profile", "about"):
            sections.summary = body
        elif key in ("core competencies", "skills", "technical skills", "core skills") \
                or "skill" in key or "competenc" in key or "tech stack" in key:
            sections.skills = (sections.skills + "\n\n" + body).strip()
        elif key in ("professional experience", "experience", "work experience") \
                or "experience" in key or "employment" in key:
            sections.experience = (sections.experience + "\n\n" + body).strip()
        elif key in ("education",) or "education" in key:
            sections.education = body
        elif key in ("certifications", "certificates") \
                or "certification" in key or "training" in key:
            sections.certifications = body
        elif key in ("projects", "key projects", "selected projects") \
                or key.startswith("project"):
            sections.projects = body
        elif key in ("key achievements", "achievements", "highlights"):
            sections.achievements = body
        else:
            sections.extra[key] = body

    if sections.achievements:
        sections.extra.setdefault("achievements", sections.achievements)

    # Re-infer name when title is generic (e.g. PDF ingest used "# Resume")
    if not _looks_like_person_name(sections.name):
        better = infer_cv_name(md, sections)
        if _looks_like_person_name(better):
            sections.name = better

    return sections


def sections_to_plain_blocks(sections: CvSections) -> dict[str, str]:
    return {
        "name": sections.name,
        "contact": sections.contact,
        "summary": sections.summary,
        "skills": sections.skills,
        "experience": sections.experience,
        "education": sections.education,
        "certifications": sections.certifications,
        "projects": sections.projects,
        # Everything real that is none of the above — awards, languages,
        # extracurriculars. Dropping it meant those lines were rendered as
        # extra bullets on the previous job, which is worse than a plain
        # "Additional" section carrying them honestly.
        "additional": "\n".join(v for v in sections.extra.values() if v).strip(),
    }
