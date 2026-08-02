"""
SmartRecruiters ATS Scraper — public API, no auth required.

Asks each board for the roles the profile targets rather than downloading the
board and filtering locally. The public postings API caps a page at 100, so a
sweep of Freshworks' 154 openings silently never saw 54 of them — and searching
that same board for "Site Reliability Engineer" returns 18 matches the sweep
reported as zero. Filtering still happens in pipeline/filter.py; this only
decides what to ask for.
"""

import logging
from datetime import datetime
from urllib.parse import urlencode

from models.job import JobRecord
from pipeline.legacy import filter_to_dicts

logger = logging.getLogger(__name__)

API = "https://api.smartrecruiters.com/v1/companies/{slug}/postings"
PAGE_LIMIT = 100
MAX_SEARCH_TERMS = 4

SMARTRECRUITERS_COMPANIES = [
    "visa", "linkedin", "informatica", "bosch", "ericsson",
    "nokia", "siemens", "philips", "sap-se", "ntt-data",
    "klarna", "adyen", "checkout-com", "rapyd", "nium",
    "stripe", "braintree", "worldline",
    "deutsche-bank", "jpmorgan", "barclays", "ubs", "credit-suisse",
    "societe-generale", "bnpparibas",
    "twilio", "sendgrid", "vonage", "messagebird", "bandwidth",
    "zendesk", "freshservice", "servicenow",
]


def _search_terms() -> list[str]:
    """Queries to send per board, most specific first.

    Mirrors the Workday scraper deliberately: one query per target title, unioned
    by the caller, so no single title can hide the others. Empty string means
    "no targeting stated" — take the whole board rather than invent a query.
    """
    import config as _cfg  # at call time: a profile save must retarget the next scan

    titles = [t.strip() for t in (getattr(_cfg, "SEARCH_KEYWORDS", None) or []) if t and t.strip()]
    if not titles:
        return [""]
    return sorted(dict.fromkeys(titles), key=len, reverse=True)[:MAX_SEARCH_TERMS]


def _record(j: dict, slug: str, today: str) -> JobRecord | None:
    job_id = j.get("id", "")
    if not job_id:
        return None
    loc = j.get("location") or {}
    location = ", ".join(str(p) for p in (loc.get("city"), loc.get("country")) if p)
    if not location and loc.get("remote"):
        location = "Remote"
    return JobRecord(
        url=f"https://jobs.smartrecruiters.com/{slug}/{job_id}",
        source="SmartRecruiters",
        company=(j.get("company") or {}).get("name") or slug.replace("-", " ").title(),
        title=j.get("name", ""),
        # Never guess a country. This used to fall back to "Remote / India",
        # which quietly tagged every location-less posting worldwide as Indian
        # and let the location gate pass rows it should have dropped.
        location=location,
        job_id=job_id,
        department=(j.get("department") or {}).get("label", ""),
        discovered_at=today,
        notes="SmartRecruiters — Apply via company site",
    )


def _scrape_company(slug: str) -> list[JobRecord]:
    from sources.fetcher import cached_get_json

    today = datetime.now().strftime("%Y-%m-%d")
    jobs: list[JobRecord] = []
    seen: set[str] = set()

    for term in _search_terms():
        offset = 0
        while True:
            params = {"status": "PUBLIC", "limit": PAGE_LIMIT, "offset": offset}
            if term:
                params["q"] = term
            url = f"{API.format(slug=slug)}?{urlencode(params)}"
            # The query string is the identity of the request, so it is also the
            # cache key — otherwise every term and page would collide on one entry.
            data = cached_get_json(url, timeout=12)
            if not isinstance(data, dict):
                break
            content = data.get("content") or []
            for j in content:
                rec = _record(j, slug, today)
                # Terms overlap: "SRE" and "Senior SRE" return the same rows.
                if rec and rec.url not in seen:
                    seen.add(rec.url)
                    jobs.append(rec)
            if len(content) < PAGE_LIMIT:
                break
            offset += PAGE_LIMIT
            if offset >= int(data.get("totalFound") or 0):
                break
    return jobs


def fetch_smartrecruiters_raw(companies: list[str] | None = None) -> list[JobRecord]:
    """Every configured board, boards in parallel.

    Different companies are different API tenants, so overlapping them adds no
    load on any single one. Terms within a board stay sequential.
    """
    from sources.parallel import parallel_flat_map

    slugs = list(companies) if companies else list(SMARTRECRUITERS_COMPANIES)
    return parallel_flat_map(slugs, _scrape_company, max_workers=8)


def scrape_smartrecruiters() -> list:
    raw = fetch_smartrecruiters_raw()
    filtered = filter_to_dicts(raw)
    by_slug: dict[str, int] = {}
    for j in filtered:
        co = j.get("company", "?")
        by_slug[co] = by_slug.get(co, 0) + 1
    for slug, count in by_slug.items():
        if count:
            logger.info(f"SmartRecruiters {slug}: {count} matches")
    return filtered
