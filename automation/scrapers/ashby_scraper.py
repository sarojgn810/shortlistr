"""
Ashby ATS Scraper — GraphQL API, raw fetch.
Filtering happens in pipeline/filter.py.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from models.job import JobRecord
from pipeline.filter import apply_discovery_filter
from portals_config import get_ashby_slugs

logger = logging.getLogger(__name__)

ASHBY_GQL = "https://jobs.ashbyhq.com/api/non-user-graphql?op=ApiJobBoardWithTeams"
GQL_QUERY = """
query ApiJobBoardWithTeams($organizationHostedJobsPageName: String!) {
  jobBoard: jobBoardWithTeams(organizationHostedJobsPageName: $organizationHostedJobsPageName) {
    teams { id name }
    jobPostings {
      id title teamId locationName employmentType
      secondaryLocations { locationName }
    }
  }
}
"""
HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (compatible; shortlistr/1.0)",
}


def _fetch_ashby_slug_result(slug: str) -> tuple[list[JobRecord], str]:
    jobs: list[JobRecord] = []
    try:
        payload = {
            "operationName": "ApiJobBoardWithTeams",
            "query": GQL_QUERY,
            "variables": {"organizationHostedJobsPageName": slug},
        }
        resp = requests.post(ASHBY_GQL, json=payload, headers=HEADERS, timeout=12)
        if resp.status_code != 200:
            return [], f"{slug}: HTTP {resp.status_code}"
        data = resp.json()
        errors = data.get("errors") or []
        if errors:
            message = str(errors[0].get("message") or "GraphQL error")
            return [], f"{slug}: {message}"
        board = (data.get("data") or {}).get("jobBoard") or {}
        postings = board.get("jobPostings", [])
        teams = {t["id"]: t["name"] for t in board.get("teams", [])}
    except Exception as e:
        return [], f"{slug}: {e}"

    for p in postings:
        secondary = [
            str(item.get("locationName") or "").strip()
            for item in (p.get("secondaryLocations") or [])
            if isinstance(item, dict) and item.get("locationName")
        ]
        locations = [str(p.get("locationName") or "").strip(), *secondary]
        loc = "; ".join(dict.fromkeys(value for value in locations if value))
        is_remote = "remote" in loc.lower()
        jobs.append(
            JobRecord(
                url=f"https://jobs.ashbyhq.com/{slug}/{p['id']}",
                source="Ashby",
                company=slug.replace("-", " ").title(),
                title=p.get("title", ""),
                location=loc,
                department=teams.get(p.get("teamId", ""), ""),
                company_email=f"careers@{slug.replace('-', '')}.com",
                job_id=str(p.get("id", "")),
                metadata={
                    "slug": slug,
                    "is_remote": is_remote,
                    "employment_type": p.get("employmentType", ""),
                },
            )
        )
    return jobs, ""


def _fetch_ashby_slug(slug: str) -> list[JobRecord]:
    """Compatibility wrapper for one board; errors are logged, never hidden."""
    jobs, error = _fetch_ashby_slug_result(slug)
    if error:
        logger.warning("Ashby %s", error)
    return jobs


def fetch_ashby_raw(companies: list | None = None) -> list[JobRecord]:
    jobs, _ = fetch_ashby_raw_with_errors(companies)
    return jobs


def fetch_ashby_raw_with_errors(
    companies: list | None = None,
) -> tuple[list[JobRecord], list[str]]:
    slugs = companies or get_ashby_slugs()
    jobs: list[JobRecord] = []
    errors: list[str] = []
    if not slugs:
        return jobs, errors
    with ThreadPoolExecutor(max_workers=min(10, len(slugs))) as executor:
        futures = {
            executor.submit(_fetch_ashby_slug_result, slug): slug for slug in slugs
        }
        for future in as_completed(futures):
            try:
                chunk, error = future.result()
            except Exception as exc:
                chunk, error = [], f"{futures[future]}: {exc}"
            jobs.extend(chunk)
            if error:
                errors.append(error)
                logger.warning("Ashby %s", error)
    return jobs, errors


def scrape_ashby(companies: list = None, log_totals: bool = False) -> list[dict]:
    raw = fetch_ashby_raw(companies)
    if log_totals:
        logger.info(f"Ashby: {len(raw)} raw (unfiltered)")
    passed, _, _ = apply_discovery_filter(raw)
    if log_totals:
        logger.info(f"Ashby total: {len(raw)} raw → {len(passed)} after discovery filter")
    return [j.to_dict() for j in passed]
