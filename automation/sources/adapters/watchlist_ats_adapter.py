"""Watchlist ATS: Greenhouse, Lever, Ashby — parallel raw fetch."""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor

from models.job import JobRecord
from scrapers.ashby_scraper import fetch_ashby_raw_with_errors
from scrapers.lever_scraper import fetch_lever_raw
from sources.adapters.greenhouse_adapter import GreenhouseAdapter
from sources.base import FetchStats, SourceAdapter

logger = logging.getLogger(__name__)


class WatchlistATSAdapter(SourceAdapter):
    name = "watchlist_ats"

    def fetch_raw(self, log_totals: bool = False) -> tuple[list[JobRecord], FetchStats]:
        t0 = time.monotonic()
        stats = FetchStats(source=self.name)
        jobs: list[JobRecord] = []

        with ThreadPoolExecutor(max_workers=3) as ex:
            gh_fut = ex.submit(GreenhouseAdapter().fetch_raw, log_totals=log_totals)
            lever_fut = ex.submit(fetch_lever_raw)
            ashby_fut = ex.submit(fetch_ashby_raw_with_errors)

            try:
                gh_jobs, gh_stats = gh_fut.result()
                jobs.extend(gh_jobs)
                stats.raw_count += gh_stats.raw_count
                if log_totals:
                    logger.info(f"Greenhouse watchlist: {gh_stats.raw_count} raw")
            except Exception as e:
                logger.warning(f"Greenhouse watchlist failed: {e}")

            for label, fut in [("Lever", lever_fut), ("Ashby", ashby_fut)]:
                try:
                    chunk = fut.result()
                    errors: list[str] = []
                    if label == "Ashby":
                        chunk, errors = chunk
                    if isinstance(chunk, list):
                        jobs.extend(chunk)
                        stats.raw_count += len(chunk)
                        if log_totals:
                            logger.info(f"{label}: {len(chunk)} raw (unfiltered)")
                    if errors and not chunk:
                        stats.error = (
                            f"Ashby returned no jobs; {len(errors)} boards failed "
                            f"({errors[0]})"
                        )
                except Exception as e:
                    logger.warning(f"{label} failed: {e}")

        stats.duration_ms = int((time.monotonic() - t0) * 1000)
        return jobs, stats
