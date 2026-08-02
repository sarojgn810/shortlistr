"""Person discovery ladder (Stage 2) — ATS/JD/URL/GitHub/SERP/title ladder.

Never scrapes LinkedIn behind login. SERP uses Serper when a key is configured.
"""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import parse_qs, quote_plus, urlparse

import requests

from prep.reach_out import extract_contacts_from_text

logger = logging.getLogger(__name__)

# Lower rank = preferred first contact (India-aware).
TITLE_LADDER: tuple[str, ...] = (
    "hiring manager",
    "engineering manager",
    "technical recruiter",
    "talent acquisition partner",
    "talent acquisition",
    "recruitment manager",
    "HR business partner",
    "head of talent acquisition",
)

_NOREPLY = ("noreply", "users.noreply.github.com", "no-reply")


def _split(full: str) -> tuple[str, str]:
    parts = [p for p in (full or "").strip().split() if p]
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[-1]


def mine_ats_people(job: dict[str, Any]) -> list[dict[str, Any]]:
    """Teamtailor-style recruiter / SmartRecruiters creator from metadata or fields."""
    out: list[dict[str, Any]] = []
    meta = job.get("metadata") if isinstance(job.get("metadata"), dict) else {}
    if isinstance(job.get("metadata_json"), str):
        try:
            import json

            meta = {**meta, **(json.loads(job["metadata_json"]) or {})}
        except Exception:
            pass

    for key in ("recruiter", "creator", "hiring_manager", "posted_by"):
        blob = meta.get(key) or job.get(key)
        if isinstance(blob, str) and blob.strip():
            first, last = _split(blob)
            out.append(
                {
                    "full_name": blob.strip(),
                    "first_name": first,
                    "last_name": last,
                    "title": key.replace("_", " "),
                    "email": "",
                    "linkedin_url": "",
                    "github_login": "",
                    "source": "ats_field",
                    "discovery_conf": 0.9,
                    "seniority_rank": 1,
                }
            )
        elif isinstance(blob, dict):
            name = (
                blob.get("name")
                or f"{blob.get('firstName') or blob.get('first_name') or ''} "
                f"{blob.get('lastName') or blob.get('last_name') or ''}"
            ).strip()
            email = str(blob.get("email") or "").strip()
            if not name and not email:
                continue
            first, last = _split(name)
            out.append(
                {
                    "full_name": name or email.split("@")[0],
                    "first_name": first,
                    "last_name": last,
                    "title": str(blob.get("title") or key),
                    "email": email,
                    "linkedin_url": str(blob.get("linkedin") or blob.get("linkedin_url") or ""),
                    "github_login": "",
                    "source": "ats_field",
                    "discovery_conf": 0.95 if email else 0.88,
                    "seniority_rank": 1,
                }
            )
    return out


def mine_jd_people(jd_text: str, apply_url: str, company: str = "") -> list[dict[str, Any]]:
    contacts = extract_contacts_from_text(jd_text or "", company=company)
    people: list[dict[str, Any]] = []
    for c in contacts:
        name = str(c.get("name") or "").strip()
        email = str(c.get("email") or "").strip()
        if not name and not email:
            continue
        first, last = _split(name or email.split("@")[0].replace(".", " "))
        src = "jd_email" if email else "jd_regex"
        people.append(
            {
                "full_name": name or first,
                "first_name": first,
                "last_name": last,
                "title": str(c.get("title") or ""),
                "email": email,
                "linkedin_url": str(c.get("linkedin_url") or ""),
                "github_login": "",
                "source": src,
                "discovery_conf": 0.85 if email else 0.7,
                "seniority_rank": 2,
            }
        )
    # mailto: on apply URL
    if (apply_url or "").lower().startswith("mailto:"):
        em = apply_url[7:].split("?")[0].strip()
        if "@" in em:
            people.append(
                {
                    "full_name": em.split("@")[0].replace(".", " ").title(),
                    "first_name": em.split("@")[0].split(".")[0],
                    "last_name": "",
                    "title": "",
                    "email": em,
                    "linkedin_url": "",
                    "github_login": "",
                    "source": "jd_email",
                    "discovery_conf": 0.9,
                    "seniority_rank": 2,
                }
            )
    return people


def apply_url_forensics(apply_url: str) -> list[dict[str, Any]]:
    """Weak evidence from query params — not a person by itself."""
    evidence: list[dict[str, Any]] = []
    try:
        qs = parse_qs(urlparse(apply_url or "").query)
    except Exception:
        return evidence
    for key in ("recruiter", "source_user", "utm_content", "gh_src", "lever-source"):
        if key in qs and qs[key]:
            evidence.append({"kind": "apply_param", "value": f"{key}={qs[key][0]}", "url": apply_url})
    return evidence


def github_emails_for_login(login: str, *, token: str = "", timeout: float = 12.0) -> list[str]:
    """Public events commit authors — skip noreply."""
    login = (login or "").strip()
    if not login:
        return []
    headers = {"User-Agent": "ShortlistrContactResolve/1.0", "Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        resp = requests.get(
            f"https://api.github.com/users/{login}/events/public",
            headers=headers,
            timeout=timeout,
            params={"per_page": 30},
        )
        if resp.status_code != 200:
            return []
        events = resp.json()
    except Exception as exc:
        logger.debug("github events failed: %s", exc)
        return []
    emails: list[str] = []
    seen: set[str] = set()
    if not isinstance(events, list):
        return []
    for ev in events:
        if not isinstance(ev, dict) or ev.get("type") != "PushEvent":
            continue
        commits = (ev.get("payload") or {}).get("commits") or []
        for c in commits:
            if not isinstance(c, dict):
                continue
            email = str((c.get("author") or {}).get("email") or "").strip().lower()
            if not email or any(n in email for n in _NOREPLY):
                continue
            if email not in seen:
                seen.add(email)
                emails.append(email)
    return emails


def search_github_org_members(company: str, *, token: str = "", limit: int = 5) -> list[dict[str, Any]]:
    """Best-effort: search users by company name (public Search API)."""
    q = (company or "").strip()
    if len(q) < 2:
        return []
    headers = {"User-Agent": "ShortlistrContactResolve/1.0", "Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        resp = requests.get(
            "https://api.github.com/search/users",
            headers=headers,
            params={"q": f"{q} in:fullname", "per_page": limit},
            timeout=12,
        )
        if resp.status_code != 200:
            return []
        items = (resp.json() or {}).get("items") or []
    except Exception as exc:
        logger.debug("github user search failed: %s", exc)
        return []
    people: list[dict[str, Any]] = []
    for it in items[:limit]:
        if not isinstance(it, dict):
            continue
        login = str(it.get("login") or "")
        if not login:
            continue
        people.append(
            {
                "full_name": login,
                "first_name": login,
                "last_name": "",
                "title": "GitHub",
                "email": "",
                "linkedin_url": "",
                "github_login": login,
                "source": "github",
                "discovery_conf": 0.45,
                "seniority_rank": 4,
            }
        )
    return people


def serper_people(
    company: str,
    persona: str,
    location: str,
    *,
    api_key: str,
    timeout: float = 15.0,
) -> list[dict[str, Any]]:
    """Public SERP snippets via Serper.dev — LinkedIn /in/ URLs only from results."""
    if not api_key:
        return []
    loc = (location or "Bangalore").split(",")[0].strip() or "Bangalore"
    query = (
        f'site:linkedin.com/in "{company}" ("{persona}") {loc}'
    )
    try:
        resp = requests.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            json={"q": query, "num": 5},
            timeout=timeout,
        )
        if resp.status_code != 200:
            logger.debug("serper HTTP %s", resp.status_code)
            return []
        data = resp.json() or {}
    except Exception as exc:
        logger.debug("serper failed: %s", exc)
        return []

    people: list[dict[str, Any]] = []
    for item in (data.get("organic") or [])[:5]:
        if not isinstance(item, dict):
            continue
        link = str(item.get("link") or "")
        title = str(item.get("title") or "")
        if "linkedin.com/in/" not in link.lower():
            continue
        # "Jane Doe - Title - Company | LinkedIn"
        name = title.split("-")[0].split("|")[0].strip()
        name = re.sub(r"\s+", " ", name)
        if len(name) < 3 or len(name) > 60:
            continue
        first, last = _split(name)
        people.append(
            {
                "full_name": name,
                "first_name": first,
                "last_name": last,
                "title": persona,
                "email": "",
                "linkedin_url": link.split("?")[0],
                "github_login": "",
                "source": "serp",
                "discovery_conf": 0.55,
                "seniority_rank": 3,
                "serp_query": query,
            }
        )
    return people


def title_ladder_people(
    company: str,
    location: str,
    job_title: str,
    *,
    api_key: str,
) -> list[dict[str, Any]]:
    """Walk TITLE_LADDER via SERP until first hit."""
    if not api_key:
        return []
    # Prefer function-specific first rung when title looks engineering
    ladder = list(TITLE_LADDER)
    jt = (job_title or "").lower()
    if any(k in jt for k in ("sre", "platform", "devops", "backend", "frontend", "engineer")):
        ladder = [
            f"{job_title.split('(')[0].strip()} manager",
            "engineering manager",
            *TITLE_LADDER[2:],
        ]
    for rank, persona in enumerate(ladder, 1):
        hits = serper_people(company, persona, location, api_key=api_key)
        if hits:
            for h in hits:
                h["seniority_rank"] = rank
                h["source"] = "title_ladder"
                h["discovery_conf"] = max(0.4, 0.65 - 0.03 * rank)
            return hits[:2]
    return []


def linkedin_search_urls(company: str, location: str = "Bangalore") -> list[dict[str, str]]:
    """Always available — user opens these themselves."""
    loc = quote_plus((location or "Bangalore").split(",")[0])
    co = quote_plus(company or "")
    return [
        {
            "label": "LinkedIn · TA / recruiter",
            "url": (
                "https://www.linkedin.com/search/results/people/"
                f"?keywords={co}%20talent%20acquisition%20{loc}"
            ),
        },
        {
            "label": "LinkedIn · engineering manager",
            "url": (
                "https://www.linkedin.com/search/results/people/"
                f"?keywords={co}%20engineering%20manager%20{loc}"
            ),
        },
    ]
