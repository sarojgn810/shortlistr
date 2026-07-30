"""
Wellfound (AngelList Talent) Scraper
Uses Wellfound's public job search via their GraphQL API.
Filtering happens in pipeline/filter.py (unified discovery filter).
"""

import logging
from datetime import datetime

import requests

from models.job import JobRecord
from pipeline.legacy import filter_to_dicts

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Content-Type": "application/json",
    "Accept": "application/json",
}

SEARCH_ROLES = [
    "site reliability engineer",
    "SRE",
    "platform engineer",
    "devops engineer",
    "aiops",
]


def fetch_wellfound_raw() -> list[JobRecord]:
    today = datetime.now().strftime("%Y-%m-%d")
    all_jobs: list[JobRecord] = []
    seen_ids: set[str] = set()

    for role in SEARCH_ROLES:
        try:
            url = "https://wellfound.com/graphql"
            query = """
            query JobSearchResults($query: String!, $locationSlug: String) {
              jobListings(query: $query, locationSlug: $locationSlug, remote: true) {
                startups {
                  id
                  name
                  jobListings {
                    id
                    title
                    remote
                    locationNames
                    jobUrl
                    description
                  }
                }
              }
            }
            """
            payload = {"query": query, "variables": {"query": role, "locationSlug": "india"}}
            resp = requests.post(url, json=payload, headers=HEADERS, timeout=15)

            if resp.status_code != 200:
                continue

            startups = (resp.json().get("data") or {}).get("jobListings", {}).get("startups", [])
            for startup in startups:
                company = startup.get("name", "")
                for j in startup.get("jobListings", []):
                    jid = str(j.get("id", ""))
                    if jid in seen_ids:
                        continue
                    seen_ids.add(jid)

                    title = j.get("title", "")
                    location = ", ".join(j.get("locationNames", [])) or (
                        "Remote" if j.get("remote") else ""
                    )
                    job_url = j.get("jobUrl", f"https://wellfound.com/jobs/{jid}")
                    snippet = (j.get("description") or "")[:800]

                    all_jobs.append(
                        JobRecord(
                            url=job_url,
                            source="Wellfound",
                            company=company,
                            title=title,
                            location=location or "Remote",
                            job_id=jid,
                            jd_text=snippet,
                            discovered_at=today,
                            notes="Wellfound — Apply via platform",
                        )
                    )
        except Exception as e:
            logger.debug(f"Wellfound '{role}' error: {e}")

    return all_jobs


def scrape_wellfound() -> list:
    raw = fetch_wellfound_raw()
    filtered = filter_to_dicts(raw)
    logger.info(f"Wellfound: {len(filtered)} matches total")
    return filtered
