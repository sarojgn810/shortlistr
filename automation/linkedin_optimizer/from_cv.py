"""Build a LinkedIn-shaped profile from the local résumé (cv.md).

This is the primary ground-truth source when LinkedIn itself cannot be scraped
(login walls). Never invent employers, metrics, or skills — only restructure
what the résumé already says.
"""

from __future__ import annotations

import re
from typing import Any

from cv.parser import infer_cv_name, parse_cv_markdown
from cv.profile_extract import _LINKEDIN_RE, _clean_url, _first_email, _first_phone
from linkedin_optimizer.parser import profile_from_structured

_SKILL_SPLIT = re.compile(r"[,|;/•·]|(?:\s{2,})")
_JOB_HEADER = re.compile(
    r"^###\s+(.+?)\s+(\w{3}\s+\d{4}\s*[–—-]\s*(?:Present|\w{3}\s+\d{4}))\s*$",
    re.I | re.M,
)
_BULLET = re.compile(r"^[-*•]\s+(.+)$", re.M)


def _split_skills(block: str) -> list[str]:
    """Pull skill tokens from a freeform skills section."""
    if not block.strip():
        return []
    # Flatten category labels ("Cloud & Platforms AWS, …") into a bag of tokens.
    text = re.sub(r"(?m)^[A-Za-z][^:\n]{2,40}:\s*", " ", block)
    text = text.replace("\n", ", ")
    text = re.sub(r"\b(SRE|AIOps|MLOps|GenAI|DevOps|DevSecOps)\s*&\s*", r"\1, ", text)
    parts = re.split(r"[,;/|•·]|(?:\s{2,})", text)
    out: list[str] = []
    seen: set[str] = set()
    stop = {
        "and", "the", "with", "for", "from", "into", "across", "using", "via",
        "root", "cause", "core", "competencies", "technical", "skills",
    }
    for p in parts:
        s = re.sub(r"[*#_]+", "", p)
        s = re.sub(r"\s+", " ", s).strip(" -–—")
        if len(s) < 2 or len(s) > 48:
            continue
        if s.lower() in stop:
            continue
        # Drop truncated fragments like "Root" left by line wraps
        if len(s) <= 4 and s.isalpha() and s.lower() not in {"aws", "gcp", "sql", "slo", "sla", "llm", "rag", "elk", "api", "sre"}:
            continue
        key = s.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out[:40]


def _parse_experience_block(block: str) -> list[dict[str, Any]]:
    """Parse ### Title Date / Company line / bullets into jobs."""
    jobs: list[dict[str, Any]] = []
    if not block.strip():
        return jobs

    # Split on ### headings
    chunks = re.split(r"(?m)^###\s+", block.strip())
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        lines = [ln.rstrip() for ln in chunk.splitlines() if ln.strip()]
        if not lines:
            continue
        header = lines[0]
        # "Site Reliability Engineer Feb 2024 – Present"
        title = re.sub(
            r"\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}.*$",
            "",
            header,
            flags=re.I,
        ).strip()
        if not title:
            title = header.strip()
        company = ""
        bullets: list[str] = []
        rest = lines[1:]
        if rest and not re.match(r"^[-*•]", rest[0]):
            # "Wipro Bangalore, India" → company = Wipro
            company_line = rest[0].strip()
            # Prefer first token cluster before a city-ish comma trail
            m = re.match(
                r"^(.+?)(?:\s+(?:Bangalore|Bengaluru|Hyderabad|Mumbai|Pune|Chennai|"
                r"Delhi|Remote|India|USA|UK).*)?$",
                company_line,
                re.I,
            )
            company = (m.group(1) if m else company_line).strip()
            # If the whole line looks like a city, keep as-is short
            if len(company) > 60:
                company = company_line.split(",")[0].strip()
            rest = rest[1:]
        # Join wrapped bullet lines
        current = ""
        for ln in rest:
            if re.match(r"^[-*•]\s+", ln):
                if current:
                    bullets.append(re.sub(r"\s+", " ", current).strip())
                current = re.sub(r"^[-*•]\s+", "", ln).strip()
            else:
                if current:
                    current = f"{current} {ln.strip()}"
                elif ln.strip():
                    # orphan continuation — treat as bullet if previous empty
                    current = ln.strip()
        if current:
            bullets.append(re.sub(r"\s+", " ", current).strip())
        if title or company or bullets:
            jobs.append({"title": title, "company": company, "bullets": bullets})
    return jobs


def profile_from_cv_markdown(md: str) -> dict[str, Any]:
    """Convert résumé markdown into a LinkedIn optimizer profile."""
    sections = parse_cv_markdown(md or "")
    name = infer_cv_name(md, sections)
    contact = sections.contact or ""
    # Headline: prefer bold line under the name, else first summary sentence role
    headline = ""
    for ln in (md or "").splitlines()[1:8]:
        s = ln.strip().strip("*").strip()
        if not s or s.startswith("#"):
            continue
        if "linkedin" in s.lower() or "@" in s or re.search(r"\+\d", s):
            continue
        if "|" in s or "Engineer" in s or "Developer" in s:
            headline = re.sub(r"[*_]+", "", s).strip()[:220]
            break
    if not headline and sections.summary:
        first = sections.summary.strip().split(".")[0].strip()
        headline = re.sub(r"[*_]+", "", first)[:220]

    location = ""
    for part in re.split(r"[•·|]", contact):
        p = part.strip()
        if not p or "@" in p or "linkedin" in p.lower() or "github" in p.lower():
            continue
        if re.search(r"\d{4,}", p):
            continue
        if re.search(r"[A-Za-z]", p) and len(p) < 60:
            location = p
            break

    li = ""
    m = _LINKEDIN_RE.search(md or "")
    if m:
        li = _clean_url(m.group(0))

    email = _first_email(md or "")
    phone = _first_phone(md or "")
    contact_bits = [b for b in (email, li, phone) if b]

    profile = profile_from_structured(
        {
            "name": name,
            "headline": headline,
            "about": (sections.summary or "").strip(),
            "experience": _parse_experience_block(sections.experience or ""),
            "skills": _split_skills(sections.skills or ""),
            "featured": (sections.projects or "").strip()[:1500],
            "open_to_work": "",
            "location": location,
            "contact": " · ".join(contact_bits),
        }
    )
    profile["linkedin_url"] = li
    profile["source"] = "cv"
    return profile


def corpus_text(profile: dict[str, Any]) -> str:
    """All evidence text used to ground keyword suggestions."""
    parts = [
        profile.get("headline") or "",
        profile.get("about") or "",
        profile.get("featured") or "",
        " ".join(profile.get("skills") or []),
    ]
    for job in profile.get("experience") or []:
        parts.append(job.get("title") or "")
        parts.append(job.get("company") or "")
        parts.extend(job.get("bullets") or [])
    return " ".join(parts)
