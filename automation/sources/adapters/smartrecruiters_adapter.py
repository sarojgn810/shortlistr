"""SmartRecruiters public postings API — no auth."""

from __future__ import annotations

import logging
import time

from portals_config import get_smartrecruiters_slugs
from scrapers.smartrecruiters_scraper import SMARTRECRUITERS_COMPANIES, fetch_smartrecruiters_raw
from sources.base import FetchStats, SourceAdapter

logger = logging.getLogger(__name__)


class SmartRecruitersAdapter(SourceAdapter):
    name = "smartrecruiters"

    def fetch_raw(self, log_totals: bool = False) -> tuple[list, FetchStats]:
        stats = FetchStats(source=self.name)
        t0 = time.monotonic()
        portals = list(get_smartrecruiters_slugs())
        jobs = fetch_smartrecruiters_raw(portals or None)
        stats.raw_count = len(jobs)
        stats.duration_ms = int((time.monotonic() - t0) * 1000)
        if log_totals:
            logger.info(
                "SmartRecruiters: %s companies → %s raw",
                len(portals or SMARTRECRUITERS_COMPANIES),
                stats.raw_count,
            )
        return jobs, stats
