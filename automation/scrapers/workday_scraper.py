"""
Workday ATS scraper — public CXS jobs API, no auth.

Boards come from portals.yml (`scan_method: workday` or myworkdayjobs.com URLs),
merged with a small built-in fallback list.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime

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


MAX_SEARCH_TERMS = 4


def _search_terms() -> list[str]:
    """The queries to ask each board for, most specific first.

    This used to send one empty search and filter the whole board locally. That
    is not just wasteful, it loses jobs: pagination stops at 60 postings, so at
    a large employer every matching role sits past the window and is never seen.
    Measured on six boards — empty search returned 360 postings and **zero**
    keepers; the same boards searched by title returned 12.

    An earlier attempt hardcoded a single "SRE" string, which hid every other
    role the user cares about. The fix for that is not to stop searching, it is
    to search once per target title and union the results, so no title can mask
    another. Capped because each term is a request per board.

    Empty list means "no targeting stated" — fall back to the full board rather
    than invent a query.
    """
    # Read at call time, not import: a profile save must retarget the next scan
    # without an API restart.
    import config as _cfg

    titles = [t.strip() for t in (getattr(_cfg, "SEARCH_KEYWORDS", None) or []) if t and t.strip()]
    if not titles:
        return [""]
    # Longest first: "Senior Site Reliability Engineer" is a better query than
    # "SRE", and dedupe is by URL so the narrower terms still add anything they
    # uniquely surface.
    ordered = sorted(dict.fromkeys(titles), key=len, reverse=True)
    return ordered[:MAX_SEARCH_TERMS]


def _search_text() -> str:
    """Back-compat single-term accessor. Prefer _search_terms()."""
    terms = _search_terms()
    return terms[0] if terms else ""


def _scrape_company(
    tenant: str,
    wd_n: str,
    site: str,
    *,
    display_name: str | None = None,
) -> list[JobRecord]:
    today = datetime.now().strftime("%Y-%m-%d")
    jobs: list[JobRecord] = []
    seen: set[str] = set()
    company = display_name or tenant.replace("-", " ").title()

    url = f"https://{tenant}.wd{wd_n}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"
    headers = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
    # One pass per target title, unioned — see _search_terms. Sequential within a
    # board on purpose: boards already run in parallel, and firing every term at
    # one tenant at once is the part that would look like abuse.
    for term in _search_terms():
        jobs.extend(_scrape_one_query(url, headers, term, tenant, wd_n, site,
                                      company, today, seen))
    return jobs


def _scrape_one_query(
    url: str,
    headers: dict,
    term: str,
    tenant: str,
    wd_n: str,
    site: str,
    company: str,
    today: str,
    seen: set[str],
) -> list[JobRecord]:
    jobs: list[JobRecord] = []
    # Paginate a few pages — enough for watchlist ROI without multi-minute hangs.
    # A keyword search usually returns under a page, so this self-limits.
    for offset in range(0, 60, 20):
        payload = {
            "appliedFacets": {},
            "limit": 20,
            "offset": offset,
            "searchText": term,
        }
        try:
            # Cached: five of these tenants take ~11s a page, and a re-scan
            # inside the TTL should not pay that again. The offset is part of
            # the cache key via the payload — same URL, different page.
            from sources.fetcher import cached_post_json

            data = cached_post_json(url, payload, headers=headers, timeout=15)
            if data is None:
                logger.debug("Workday %s: no data at offset %s", tenant, offset)
                break
            postings = data.get("jobPostings") or []
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
                # Terms overlap by design — "Senior Site Reliability Engineer"
                # and "SRE" return many of the same postings.
                key = full_url or f"{company}|{title}"
                if key in seen:
                    continue
                seen.add(key)
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
    """Scrape every configured Workday board, boards in parallel.

    This used to be a plain for-loop, which made Workday ~97% of a whole scan:
    15 boards x up to 3 pages, one request at a time. Measured per board, five
    tenants answered in ~34s each while the other ten took 1-8s for the same 60
    postings — so the cost was almost entirely waiting on a handful of slow
    hosts, in series.

    Every board is a different myworkdayjobs tenant, so running them together
    adds no load on any single host — each worker is talking to a different
    server. Pagination inside a board stays sequential: offsets are walked in
    order and the loop breaks early on a short page.
    """
    # Imported here, not at module scope: `sources/__init__` builds the registry,
    # which imports the Workday adapter, which imports this module.
    from sources.parallel import parallel_flat_map

    boards = _company_list()

    def _one(board: tuple[str, str, str, str]) -> list[JobRecord]:
        tenant, wd_n, site, display = board
        chunk = _scrape_company(tenant, wd_n, site, display_name=display)
        if chunk:
            logger.info("Workday %s: %s raw", display or tenant, len(chunk))
        return chunk

    return parallel_flat_map(boards, _one, max_workers=10)


def scrape_workday() -> list:
    raw = fetch_workday_raw()
    filtered = filter_to_dicts(raw)
    by_tenant: dict[str, int] = {}
    for j in filtered:
        by_tenant[j.get("company", "?")] = by_tenant.get(j.get("company", "?"), 0) + 1
    for tenant, count in by_tenant.items():
        logger.info("Workday %s: %s matches", tenant, count)
    return filtered
