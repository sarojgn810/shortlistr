"""Remotive — raw fetch; filtering in pipeline/filter.py."""

import logging

import requests

from models.job import JobRecord
from pipeline.filter import apply_discovery_filter

logger = logging.getLogger(__name__)

REMOTIVE_CATEGORIES = ["devops-sysadmin", "software-dev", "data"]


def fetch_remotive_raw() -> list[JobRecord]:
    jobs: list[JobRecord] = []
    seen: set[str] = set()
    for category in REMOTIVE_CATEGORIES:
        url = f"https://remotive.com/api/remote-jobs?category={category}&limit=100"
        try:
            resp = requests.get(url, timeout=15)
            if resp.status_code != 200:
                continue
            data = resp.json()
        except Exception:
            continue
        for job in data.get("jobs", []):
            job_id = str(job.get("id", ""))
            if job_id in seen:
                continue
            seen.add(job_id)
            jobs.append(
                JobRecord(
                    url=job.get("url", ""),
                    source="Remotive",
                    company=job.get("company_name", ""),
                    title=job.get("title", ""),
                    location=job.get("candidate_required_location", "Remote"),
                    jd_text=(job.get("description", "") or "")[:800],
                    salary=job.get("salary", ""),
                    department=job.get("category", ""),
                    job_id=job_id,
                )
            )
    return jobs


def scrape_remotive(log_totals: bool = False) -> list[dict]:
    raw = fetch_remotive_raw()
    if log_totals:
        logger.info(f"Remotive: {len(raw)} raw (unfiltered)")
    passed, _, _ = apply_discovery_filter(raw)
    if log_totals:
        logger.info(f"Remotive: {len(raw)} raw → {len(passed)} after discovery filter")
    return [j.to_dict() for j in passed]
