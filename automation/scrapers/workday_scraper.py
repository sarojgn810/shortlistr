"""
Workday ATS scraper — public CXS jobs API, no auth.

Boards come from portals.yml (`scan_method: workday` or myworkdayjobs.com URLs),
merged with a small built-in fallback list.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime

import requests

from models.job import JobRecord
from pipeline.legacy import filter_to_dicts

logger = logging.getLogger(__name__)

# Fallback when portals.yml has no Workday rows yet.
_FALLBACK_COMPANIES: list[tuple[str, str, str, str]] = [
    # tenant, wd_n, site, display_name
    ("ibm", "5", "IBMJOBS", "IBM"),
    ("cisco", "5", "External_Job_Board_To_Use", "Cisco"),
    ("adobe", "5", "external_experienced", "Adobe"),
]


def parse_workday_url(url: str) -> tuple[str, str, str] | None:
    """Compat wrapper — canonical parser lives in portals_config."""
    from portals_config import parse_workday_url as _parse

    return _parse(url)


def _boards_from_portals() -> list[tuple[str, str, str, str]]:
    try:
        from portals_config import get_workday_boards

        return get_workday_boards()
    except Exception as exc:
        logger.debug("Workday portals load failed: %s", exc)
        return []


def _company_list() -> list[tuple[str, str, str, str]]:
    boards = _boards_from_portals()
    if boards:
        return boards
    return list(_FALLBACK_COMPANIES)


def _search_text() -> str:
    """Prefer an empty search so the profile gate sees the full board.

    A hardcoded SRE string used to hide every other role before filtering.
    """
    return ""


def _scrape_company(
    tenant: str,
    wd_n: str,
    site: str,
    *,
    display_name: str | None = None,
) -> list[JobRecord]:
    today = datetime.now().strftime("%Y-%m-%d")
    jobs: list[JobRecord] = []
    company = display_name or tenant.replace("-", " ").title()

    url = f"https://{tenant}.wd{wd_n}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"
    headers = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
    # Paginate a few pages — enough for watchlist ROI without multi-minute hangs.
    for offset in range(0, 60, 20):
        payload = {
            "appliedFacets": {},
            "limit": 20,
            "offset": offset,
            "searchText": _search_text(),
        }
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=15)
            if resp.status_code != 200:
                logger.debug("Workday %s: HTTP %s", tenant, resp.status_code)
                break
            postings = resp.json().get("jobPostings") or []
            if not postings:
                break
            for j in postings:
                title = j.get("title", "")
                location = j.get("locationsText", "") or j.get("primaryLocation", "")
                ext_url = j.get("externalPath", "")
                job_id = j.get("bulletFields", [""])[0] if j.get("bulletFields") else ext_url
                full_url = (
                    f"https://{tenant}.wd{wd_n}.myworkdayjobs.com/{site}{ext_url}"
                    if ext_url
                    else ""
                )
                jobs.append(
                    JobRecord(
                        url=full_url,
                        source="Workday",
                        company=company,
                        title=title,
                        location=location or "",
                        job_id=str(job_id or ext_url or ""),
                        department=j.get("jobFamilyGroup", ""),
                        discovered_at=today,
                        notes=(
                            f"Workday — Apply at {full_url}"
                            if full_url
                            else "Workday — Apply via company site"
                        ),
                    )
                )
            if len(postings) < 20:
                break
        except Exception as e:
            logger.debug("Workday %s error: %s", tenant, e)
            break

    return jobs


def fetch_workday_raw() -> list[JobRecord]:
    all_jobs: list[JobRecord] = []
    for tenant, wd_n, site, display in _company_list():
        chunk = _scrape_company(tenant, wd_n, site, display_name=display)
        if chunk:
            logger.info("Workday %s: %s raw", display or tenant, len(chunk))
        all_jobs.extend(chunk)
    return all_jobs


def scrape_workday() -> list:
    raw = fetch_workday_raw()
    filtered = filter_to_dicts(raw)
    by_tenant: dict[str, int] = {}
    for j in filtered:
        by_tenant[j.get("company", "?")] = by_tenant.get(j.get("company", "?"), 0) + 1
    for tenant, count in by_tenant.items():
        logger.info("Workday %s: %s matches", tenant, count)
    return filtered
