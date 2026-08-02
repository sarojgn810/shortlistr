"""Greenhouse source adapter — raw fetch, no title filter."""

from __future__ import annotations

import logging
import time

from models.job import JobRecord
from portals_config import get_greenhouse_slugs
from sources.base import FetchStats, SourceAdapter
from sources.fetcher import cached_get_json
from sources.parallel import parallel_flat_map

logger = logging.getLogger(__name__)


def _fetch_greenhouse_slug(slug: str) -> list[JobRecord]:
    url = f"https://api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
    data = cached_get_json(url, cache_key=f"gh/{slug}", timeout=12)
    if not data:
        return []

    jobs: list[JobRecord] = []
    for job in data.get("jobs", []):
        content = job.get("content", "") or ""
        dept = ""
        if job.get("departments"):
            dept = job["departments"][0].get("name", "")
        jobs.append(
            JobRecord(
                url=job.get("absolute_url", ""),
                source="Greenhouse",
                company=slug.replace("-", " ").title(),
                title=job.get("title", ""),
                location=(job.get("location") or {}).get("name", ""),
                jd_text=content,
                department=dept,
                company_email=f"careers@{slug.replace('-', '')}.com",
                metadata={"slug": slug},
            )
        )
    return jobs


class GreenhouseAdapter(SourceAdapter):
    name = "greenhouse"

    def fetch_raw(self, log_totals: bool = False) -> tuple[list[JobRecord], FetchStats]:
        companies = get_greenhouse_slugs()
        stats = FetchStats(source=self.name)
        t0 = time.monotonic()

        jobs = parallel_flat_map(companies, _fetch_greenhouse_slug, max_workers=10)
        stats.raw_count = len(jobs)

        if log_totals:
            logger.info(
                f"Greenhouse: {len(companies)} slugs → {stats.raw_count} raw records (parallel)"
            )

        stats.duration_ms = int((time.monotonic() - t0) * 1000)
        return jobs, stats
