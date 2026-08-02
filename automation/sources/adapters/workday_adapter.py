"""Workday boards from portals.yml — public CXS jobs API, no auth."""

from __future__ import annotations

import logging
import time

from scrapers.workday_scraper import fetch_workday_raw
from sources.base import FetchStats, SourceAdapter

logger = logging.getLogger(__name__)


class WorkdayAdapter(SourceAdapter):
    name = "workday"

    def fetch_raw(self, log_totals: bool = False) -> tuple[list, FetchStats]:
        t0 = time.monotonic()
        stats = FetchStats(source=self.name)
        try:
            jobs = fetch_workday_raw()
            stats.raw_count = len(jobs)
            if log_totals:
                logger.info("Workday watchlist: %s raw", len(jobs))
        except Exception as e:
            stats.error = str(e)
            logger.warning("Workday watchlist failed: %s", e)
            jobs = []
        stats.duration_ms = int((time.monotonic() - t0) * 1000)
        return jobs, stats
