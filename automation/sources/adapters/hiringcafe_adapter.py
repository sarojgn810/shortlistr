"""hiring.cafe — sitemap-driven, keyword-first.

The scraper filters postings by slug before fetching any page, so this is a
narrow read of a large board rather than a crawl of it. See the scraper module
for the robots.txt reasoning, including why Dice is not alongside it.
"""

from __future__ import annotations

import logging
import time

from scrapers.hiringcafe_scraper import fetch_jobs
from sources.base import FetchStats, SourceAdapter

logger = logging.getLogger(__name__)


class HiringCafeAdapter(SourceAdapter):
    name = "hiringcafe"

    def fetch_raw(self, log_totals: bool = False) -> tuple[list, FetchStats]:
        stats = FetchStats(source=self.name)
        t0 = time.monotonic()
        try:
            jobs = fetch_jobs()
        except Exception as exc:
            # One board being unreachable must not end a scan.
            logger.warning("hiring.cafe failed: %s", exc)
            stats.error = str(exc)[:200]
            jobs = []
        stats.raw_count = len(jobs)
        stats.duration_ms = int((time.monotonic() - t0) * 1000)
        if log_totals:
            logger.info("hiring.cafe: %s raw", stats.raw_count)
        return jobs, stats
