"""
Ashby ATS Scraper — GraphQL API, raw fetch.
Filtering happens in pipeline/filter.py.
"""

import logging

import requests

from models.job import JobRecord
from pipeline.filter import apply_discovery_filter
from portals_config import get_ashby_slugs
from sources.parallel import parallel_flat_map

logger = logging.getLogger(__name__)

ASHBY_GQL = "https://jobs.ashbyhq.com/api/non-user-graphql?op=ApiJobBoardWithTeams"
GQL_QUERY = """
query ApiJobBoardWithTeams($organizationHostedJobsPageName: String!) {
  jobBoard: jobBoardWithTeams(organizationHostedJobsPageName: $organizationHostedJobsPageName) {
    teams { id name }
    jobPostings {
      id title teamId locationName isRemote externalLink
    }
  }
}
"""
HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (compatible; shortlistr/1.0)",
}


def _fetch_ashby_slug(slug: str) -> list[JobRecord]:
    jobs: list[JobRecord] = []
    try:
        payload = {
            "operationName": "ApiJobBoardWithTeams",
            "query": GQL_QUERY,
            "variables": {"organizationHostedJobsPageName": slug},
        }
        resp = requests.post(ASHBY_GQL, json=payload, headers=HEADERS, timeout=12)
        if resp.status_code != 200:
            return []
        board = resp.json().get("data", {}).get("jobBoard") or {}
        postings = board.get("jobPostings", [])
        teams = {t["id"]: t["name"] for t in board.get("teams", [])}
    except Exception as e:
        logger.warning(f"Ashby {slug} error: {e}")
        return []

    for p in postings:
        is_remote = p.get("isRemote", False)
        loc = p.get("locationName", "") or ("Remote" if is_remote else "")
        jobs.append(
            JobRecord(
                url=p.get("externalLink") or f"https://jobs.ashbyhq.com/{slug}/{p['id']}",
                source="Ashby",
                company=slug.replace("-", " ").title(),
                title=p.get("title", ""),
                location=loc,
                department=teams.get(p.get("teamId", ""), ""),
                company_email=f"careers@{slug.replace('-', '')}.com",
                job_id=str(p.get("id", "")),
                metadata={"slug": slug, "is_remote": is_remote},
            )
        )
    return jobs


def fetch_ashby_raw(companies: list | None = None) -> list[JobRecord]:
    slugs = companies or get_ashby_slugs()
    return parallel_flat_map(slugs, _fetch_ashby_slug, max_workers=10)


def scrape_ashby(companies: list = None, log_totals: bool = False) -> list[dict]:
    raw = fetch_ashby_raw(companies)
    if log_totals:
        logger.info(f"Ashby: {len(raw)} raw (unfiltered)")
    passed, _, _ = apply_discovery_filter(raw)
    if log_totals:
        logger.info(f"Ashby total: {len(raw)} raw → {len(passed)} after discovery filter")
    return [j.to_dict() for j in passed]
