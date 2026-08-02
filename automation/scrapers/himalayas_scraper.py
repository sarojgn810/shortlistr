"""Himalayas — raw fetch; filtering in pipeline/filter.py."""

import logging

import requests

import config as _cfg
from models.job import JobRecord
from pipeline.filter import apply_discovery_filter

logger = logging.getLogger(__name__)
HIMALAYAS_API = "https://himalayas.app/jobs/api"


def _aggregator_queries(max_queries: int = 6) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for kw in _cfg.SEARCH_KEYWORDS:
        q = kw.strip()
        key = q.lower()
        if len(key) < 3 or key in seen:
            continue
        seen.add(key)
        out.append(q)
        if len(out) >= max_queries:
            break
    return out or ["site reliability engineer", "devops engineer", "platform engineer"]


def fetch_himalayas_raw() -> list[JobRecord]:
    jobs: list[JobRecord] = []
    seen: set[str] = set()
    for q in _aggregator_queries():
        try:
            resp = requests.get(
                HIMALAYAS_API,
                params={"q": q, "limit": 50, "remoteOnly": "true"},
                timeout=15,
            )
            if resp.status_code != 200:
                continue
            data = resp.json()
        except Exception:
            continue
        for job in data.get("jobs", []):
            job_id = str(job.get("slug", job.get("id", "")))
            if job_id in seen:
                continue
            seen.add(job_id)
            salary = ""
            if job.get("minSalary") and job.get("maxSalary"):
                currency = job.get("salaryCurrency", "USD")
                salary = f"{currency} {job['minSalary']:,} – {job['maxSalary']:,}"
            jobs.append(
                JobRecord(
                    url=f"https://himalayas.app/jobs/{job_id}",
                    source="Himalayas",
                    company=job.get("companyName", ""),
                    title=job.get("title", ""),
                    location="Remote",
                    jd_text=(job.get("description", "") or ""),
                    salary=salary,
                    department=(job.get("categories") or [""])[0] if job.get("categories") else "",
                    job_id=job_id,
                )
            )
    return jobs


def scrape_himalayas(log_totals: bool = False) -> list[dict]:
    raw = fetch_himalayas_raw()
    if log_totals:
        logger.info(f"Himalayas: {len(raw)} raw (unfiltered)")
    passed, _, _ = apply_discovery_filter(raw)
    if log_totals:
        logger.info(f"Himalayas: {len(raw)} raw → {len(passed)} after discovery filter")
    return [j.to_dict() for j in passed]
