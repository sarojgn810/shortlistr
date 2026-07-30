"""Naukri adapter — Indian job board search via public API (no login)."""

from __future__ import annotations

import logging
import time

from models.job import JobRecord
from sources.base import FetchStats, SourceAdapter

logger = logging.getLogger(__name__)


class NaukriAdapter(SourceAdapter):
    name = "naukri"

    def fetch_raw(self, log_totals: bool = False) -> tuple[list[JobRecord], FetchStats]:
        stats = FetchStats(source=self.name)
        t0 = time.monotonic()

        try:
            from scrapers.naukri_scraper import scrape_naukri

            raw = scrape_naukri()
        except Exception as e:
            logger.warning("Naukri scraper failed: %s", e)
            raw = []

        jobs: list[JobRecord] = []
        for r in raw:
            url = r.get("url", "")
            if not url.strip():
                continue
            meta = dict(r.get("metadata") or {})
            jobs.append(
                JobRecord(
                    url=url,
                    source="Naukri",
                    company=r.get("company", ""),
                    title=r.get("title", ""),
                    location=r.get("location", ""),
                    jd_text=r.get("jd_snippet", ""),
                    salary=r.get("salary", "") or "",
                    notes=r.get("notes", "") or "Naukri",
                    metadata=meta,
                )
            )

        stats.raw_count = len(raw)
        stats.duration_ms = int((time.monotonic() - t0) * 1000)
        if log_totals:
            logger.info("Naukri: %d raw → %d records", len(raw), len(jobs))
        return jobs, stats
