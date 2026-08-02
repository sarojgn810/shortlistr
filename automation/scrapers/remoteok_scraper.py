"""RemoteOK — raw fetch; filtering in pipeline/filter.py."""

import logging

import requests

import config as _cfg
from models.job import JobRecord
from pipeline.filter import apply_discovery_filter

logger = logging.getLogger(__name__)
REMOTEOK_API = "https://remoteok.com/api"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; shortlistr-bot/1.0)"}

# RemoteOK exposes tags, not free-text search, so map role families onto them.
# Keyed by config.title_family so "Senior MLOps Engineer" resolves like "MLOps".
_FAMILY_TO_TAG = {
    "sre": "devops",
    "devops": "devops",
    "platform": "devops",
    "infrastructure": "devops",
    "mlops": "devops",
    "aiops": "devops",
    "cloud": "cloud",
    "kubernetes": "devops",
}


def _tags_from_keywords() -> list[str]:
    seen: set[str] = set()
    for kw in _cfg.SEARCH_KEYWORDS:
        tag = _FAMILY_TO_TAG.get(_cfg.title_family(kw))
        if tag and tag not in seen:
            seen.add(tag)
    return list(seen) or ["devops"]


def _fetch_tag(tag: str) -> list[JobRecord]:
    jobs: list[JobRecord] = []
    try:
        resp = requests.get(REMOTEOK_API, params={"tag": tag}, headers=HEADERS, timeout=20)
        if resp.status_code != 200:
            return jobs
        data = resp.json()
    except Exception:
        return jobs
    for job in data[1:]:
        if not isinstance(job, dict):
            continue
        salary = ""
        if job.get("salary_min") and job.get("salary_max"):
            salary = f"${job['salary_min']:,} – ${job['salary_max']:,}/yr"
        jobs.append(
            JobRecord(
                url=job.get("url", f"https://remoteok.com/l/{job.get('id', '')}"),
                source="RemoteOK",
                company=job.get("company", ""),
                title=job.get("position", ""),
                location="Remote",
                jd_text=(job.get("description", "") or ""),
                salary=salary,
                department=" ".join(job.get("tags", []))[:100],
                job_id=str(job.get("id", "")),
            )
        )
    return jobs


def fetch_remoteok_raw() -> list[JobRecord]:
    seen: set[str] = set()
    jobs: list[JobRecord] = []
    for tag in _tags_from_keywords():
        for j in _fetch_tag(tag):
            if j.job_id not in seen:
                seen.add(j.job_id)
                jobs.append(j)
    return jobs


def scrape_remoteok(log_totals: bool = False) -> list[dict]:
    raw = fetch_remoteok_raw()
    if log_totals:
        logger.info(f"RemoteOK: {len(raw)} raw (unfiltered)")
    passed, _, _ = apply_discovery_filter(raw)
    if log_totals:
        logger.info(f"RemoteOK: {len(raw)} raw → {len(passed)} after discovery filter")
    return [j.to_dict() for j in passed]
