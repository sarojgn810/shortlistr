"""Prep Reach out — contacts from the JD + LinkedIn deep links (no paid enrichment).

We never scrape LinkedIn People Search or auto-message. Extract what the posting
already says, surface openable search URLs, and let the user paste/edit contacts.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any
from urllib.parse import quote_plus

_EMAIL_RE = re.compile(
    r"(?<![A-Za-z0-9._%+-])([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})(?![A-Za-z0-9._%+-])"
)
_LINKEDIN_IN_RE = re.compile(
    r"https?://(?:www\.)?linkedin\.com/in/([A-Za-z0-9_-]+)/?",
    re.I,
)
# Labels that introduce a person — require a separator OR a dedicated verb phrase.
_CONTACT_NAME_RE = re.compile(
    r"(?:"
    r"(?i:contact|recruiter|hiring\s+manager|talent\s+(?:partner|acquisition)|"
    r"posted\s+by|questions\?\s*email|for\s+questions)\s*[:\-–—]\s*"
    r"|"
    r"(?i:reach\s+out\s+to|talk\s+to|apply\s+(?:to|via))\s+"
    r")"
    r"([A-Z][a-zA-Z'’.-]+(?:\s+[A-Z][a-zA-Z'’.-]+){0,3})"
)
_NAME_BEFORE_EMAIL_RE = re.compile(
    r"([A-Z][a-zA-Z'’.-]+(?:\s+[A-Z][a-zA-Z'’.-]+){1,2})\s*"
    r"(?:[\(<\[,]|\s[-–—]\s)?\s*"
    r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})"
)
_TITLE_HINT_RE = re.compile(
    r"(?i)\b("
    r"recruiter|talent\s+(?:acquisition|partner|sourcer)|"
    r"hiring\s+manager|people\s+partner|sourcer|"
    r"staffing|hr\s+business\s+partner"
    r")\b"
)

# Generic inbox local-parts often invented by ATS scrapers — only keep if in JD.
_GENERIC_LOCAL = frozenset(
    {"careers", "jobs", "hr", "recruiting", "talent", "apply", "noreply", "no-reply"}
)


def _contact_id(*parts: str) -> str:
    raw = "|".join(p.strip().lower() for p in parts if p and str(p).strip())
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12] if raw else "unknown"


def _clean_name(name: str) -> str:
    n = re.sub(r"\s+", " ", (name or "").strip(" \t\r\n,.;:|-"))
    # Drop obvious non-names
    if len(n) < 2 or len(n) > 60:
        return ""
    if "@" in n or "http" in n.lower():
        return ""
    skip = {"the", "our", "team", "please", "email", "us", "here", "below"}
    if n.lower() in skip:
        return ""
    return n


def _dedupe_key(c: dict[str, Any]) -> str:
    email = (c.get("email") or "").strip().lower()
    li = (c.get("linkedin_url") or "").strip().lower().rstrip("/")
    name = (c.get("name") or "").strip().lower()
    if email:
        return f"e:{email}"
    if li:
        return f"l:{li}"
    if name:
        return f"n:{name}"
    return f"id:{c.get('id') or ''}"


def extract_contacts_from_text(
    text: str,
    *,
    company: str = "",
    company_email: str = "",
) -> list[dict[str, Any]]:
    """Pull emails, LinkedIn /in/ URLs, and nearby names from posting text."""
    jd = text or ""
    contacts: list[dict[str, Any]] = []
    by_email: dict[str, dict[str, Any]] = {}
    by_li: dict[str, dict[str, Any]] = {}

    for m in _NAME_BEFORE_EMAIL_RE.finditer(jd):
        name = _clean_name(m.group(1))
        email = m.group(2).strip()
        if not email:
            continue
        c = {
            "id": _contact_id(email),
            "name": name,
            "title": "",
            "email": email,
            "linkedin_url": "",
            "note": "Found next to an email in the job description.",
            "source": "jd",
        }
        by_email[email.lower()] = c

    for m in _EMAIL_RE.finditer(jd):
        email = m.group(1).strip()
        key = email.lower()
        if key in by_email:
            continue
        # Look a bit left of the match for a name label
        start = max(0, m.start() - 80)
        window = jd[start : m.start()]
        name = ""
        label = _CONTACT_NAME_RE.search(window)
        if label:
            name = _clean_name(label.group(1))
        by_email[key] = {
            "id": _contact_id(email),
            "name": name,
            "title": "",
            "email": email,
            "linkedin_url": "",
            "note": "Email listed in the job description.",
            "source": "jd",
        }

    for m in _LINKEDIN_IN_RE.finditer(jd):
        slug = m.group(1)
        url = f"https://www.linkedin.com/in/{slug}"
        key = url.lower()
        if key in by_li:
            continue
        # Prefer a nearby contact label as the display name
        start = max(0, m.start() - 100)
        window = jd[start : m.start()]
        name = ""
        label = _CONTACT_NAME_RE.search(window)
        if label:
            name = _clean_name(label.group(1))
        if not name:
            # linkedin slug → rough display (jane-doe → Jane Doe)
            name = _clean_name(slug.replace("-", " ").replace("_", " ").title())
        by_li[key] = {
            "id": _contact_id(url),
            "name": name,
            "title": "",
            "email": "",
            "linkedin_url": url,
            "note": "LinkedIn profile link in the job description.",
            "source": "jd",
        }

    # Named contacts without email/URL (still useful for LinkedIn search)
    for m in _CONTACT_NAME_RE.finditer(jd):
        name = _clean_name(m.group(1))
        if not name:
            continue
        # Skip if already captured via email/li nearby
        already = any(
            (c.get("name") or "").lower() == name.lower()
            for c in list(by_email.values()) + list(by_li.values())
        )
        if already:
            continue
        title = ""
        # Title hint on same line
        line_start = jd.rfind("\n", 0, m.start()) + 1
        line_end = jd.find("\n", m.end())
        if line_end < 0:
            line_end = len(jd)
        line = jd[line_start:line_end]
        th = _TITLE_HINT_RE.search(line)
        if th:
            title = th.group(1).strip().title()
        contacts.append(
            {
                "id": _contact_id("name", name, company),
                "name": name,
                "title": title,
                "email": "",
                "linkedin_url": "",
                "note": "Named in the job description — open a LinkedIn search to find them.",
                "source": "jd",
            }
        )

    contacts.extend(by_email.values())
    contacts.extend(by_li.values())

    # company_email only when also present in the JD (avoid invented careers@).
    ce = (company_email or "").strip()
    if ce and ce.lower() in jd.lower():
        key = ce.lower()
        if key not in by_email:
            local = ce.split("@", 1)[0].lower()
            note = "Email on the job row (also in the posting)."
            if local in _GENERIC_LOCAL:
                note = "Careers inbox from the posting."
            contacts.append(
                {
                    "id": _contact_id(ce),
                    "name": "",
                    "title": "",
                    "email": ce,
                    "linkedin_url": "",
                    "note": note,
                    "source": "jd",
                }
            )

    return _dedupe_contacts(contacts)


def linkedin_search_links(company: str, role: str = "") -> list[dict[str, str]]:
    """Openable LinkedIn search URLs — user clicks; we do not scrape results."""
    company = (company or "").strip()
    role = (role or "").strip()
    if not company:
        return []

    links: list[dict[str, str]] = []
    recruiter_q = f"Recruiter OR \"Talent Acquisition\" {company}"
    links.append(
        {
            "label": f"Recruiters at {company}",
            "url": (
                "https://www.linkedin.com/search/results/people/"
                f"?keywords={quote_plus(recruiter_q)}"
            ),
        }
    )
    if role:
        hm_q = f"\"Hiring Manager\" OR \"Engineering Manager\" {role} {company}"
        links.append(
            {
                "label": f"Hiring managers — {role}",
                "url": (
                    "https://www.linkedin.com/search/results/people/"
                    f"?keywords={quote_plus(hm_q)}"
                ),
            }
        )
    links.append(
        {
            "label": f"{company} on LinkedIn",
            "url": (
                "https://www.linkedin.com/search/results/companies/"
                f"?keywords={quote_plus(company)}"
            ),
        }
    )
    links.append(
        {
            "label": f"People at {company}",
            "url": (
                "https://www.linkedin.com/search/results/people/"
                f"?keywords={quote_plus(company)}"
            ),
        }
    )
    return links


def draft_outreach_message(
    *,
    company: str,
    role: str,
    contact_name: str = "",
    candidate_name: str = "",
    yoe: str = "",
) -> str:
    """Short LinkedIn/email outreach the user copies — never auto-sent."""
    company = (company or "your team").strip() or "your team"
    role = (role or "the role").strip() or "the role"
    greet = f"Hi {contact_name.split()[0]}," if contact_name.strip() else "Hi,"
    who = (candidate_name or "").strip() or "I"
    yoe_bit = f" with {yoe}+ years of relevant experience" if str(yoe).strip() else ""
    body = (
        f"{greet}\n\n"
        f"I saw the {role} opening at {company} and wanted to reach out directly. "
        f"{who}{yoe_bit} — happy to share a short note on fit or jump on a quick call "
        f"if useful.\n\n"
        f"Thanks for your time,\n"
        f"{(candidate_name or '').strip()}"
    ).strip()
    try:
        from writing.sanitize import sanitize

        return sanitize(body, mode="prose")
    except Exception:
        return body


def normalize_user_contact(raw: dict[str, Any]) -> dict[str, Any] | None:
    name = _clean_name(str(raw.get("name") or ""))
    email = str(raw.get("email") or "").strip()
    li = str(raw.get("linkedin_url") or "").strip()
    title = str(raw.get("title") or "").strip()[:80]
    note = str(raw.get("note") or "").strip()[:240]
    if email:
        em = _EMAIL_RE.search(email)
        email = em.group(1) if em else ""
    if li:
        m = _LINKEDIN_IN_RE.search(li)
        li = f"https://www.linkedin.com/in/{m.group(1)}" if m else ""
    if not (name or email or li):
        return None
    cid = str(raw.get("id") or "").strip() or _contact_id(email or li or name)
    return {
        "id": cid,
        "name": name,
        "title": title,
        "email": email,
        "linkedin_url": li,
        "note": note or "Added by you.",
        "source": "user",
    }


def _dedupe_contacts(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for c in items:
        if not isinstance(c, dict):
            continue
        key = _dedupe_key(c)
        if not key or key in seen:
            # Merge richer fields into existing
            if key in seen:
                for existing in out:
                    if _dedupe_key(existing) == key:
                        for field in ("name", "title", "email", "linkedin_url", "note"):
                            if not existing.get(field) and c.get(field):
                                existing[field] = c[field]
                        break
            continue
        seen.add(key)
        out.append(c)
    return out


def merge_contacts(
    jd_contacts: list[dict[str, Any]],
    user_contacts: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    normalized_user: list[dict[str, Any]] = []
    for raw in user_contacts or []:
        if not isinstance(raw, dict):
            continue
        n = normalize_user_contact(raw)
        if n:
            normalized_user.append(n)
    # Start with JD extracts, then overlay user entries (same email/li/name wins).
    by_key: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for c in [*jd_contacts, *normalized_user]:
        key = _dedupe_key(c)
        if not key:
            continue
        if key not in by_key:
            order.append(key)
        by_key[key] = c
    return [by_key[k] for k in order]


def build_reach_out(
    job: dict[str, Any],
    *,
    user_contacts: list[dict[str, Any]] | None = None,
    outreach_draft: str | None = None,
) -> dict[str, Any]:
    """Assemble the Prep Reach out payload for one job."""
    company = str(job.get("company") or "").strip()
    role = str(job.get("title") or job.get("role") or "").strip()
    jd = str(job.get("jd_text") or job.get("jd_snippet") or "")
    company_email = str(job.get("company_email") or "").strip()

    jd_contacts = extract_contacts_from_text(
        jd, company=company, company_email=company_email
    )
    contacts = merge_contacts(jd_contacts, user_contacts)

    try:
        from config import CANDIDATE

        cand = CANDIDATE or {}
    except Exception:
        cand = {}

    primary_name = next((c.get("name") or "" for c in contacts if c.get("name")), "")
    generated = draft_outreach_message(
        company=company,
        role=role,
        contact_name=primary_name,
        candidate_name=str(cand.get("name") or ""),
        yoe=str(cand.get("years_exp") or ""),
    )
    draft = (outreach_draft or "").strip() or generated

    return {
        "contacts": contacts,
        "searches": linkedin_search_links(company, role),
        "outreach_draft": draft,
        "outreach_generated": generated,
        "disclaimer": (
            "We only list contacts found in the job description or that you add. "
            "LinkedIn links open search in your browser — we do not scrape profiles "
            "or send messages."
        ),
    }
