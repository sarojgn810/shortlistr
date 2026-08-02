"""Search discovery adapter — portals.yml search_queries."""

from __future__ import annotations

import logging
import time

import yaml

from models.job import JobRecord
from paths import PORTALS_PATH
from processors.scan_portals import build_title_filter
from processors.search_discovery import discover_from_search
from sources.base import FetchStats, SourceAdapter

logger = logging.getLogger(__name__)


class SearchDiscoveryAdapter(SourceAdapter):
    name = "search"

    def fetch_raw(self, log_totals: bool = False) -> tuple[list[JobRecord], FetchStats]:
        stats = FetchStats(source=self.name)
        t0 = time.monotonic()
        jobs: list[JobRecord] = []

        title_filter_fn = None
        if PORTALS_PATH and __import__("os").path.exists(PORTALS_PATH):
            cfg = yaml.safe_load(open(PORTALS_PATH, encoding="utf-8")) or {}
            title_filter_fn = build_title_filter(cfg.get("title_filter"))

        offers, search_stats = discover_from_search(
            title_filter=title_filter_fn,
            check_liveness=True,
        )
        stats.raw_count = search_stats.get("ats_urls", 0)
        stats.error = str(search_stats.get("error") or "")
        for o in offers:
            jobs.append(
                JobRecord(
                    url=o.get("url", ""),
                    source="SearchDiscovery",
                    company=o.get("company", ""),
                    title=o.get("title", ""),
                    location=o.get("location", ""),
                    notes="search_queries",
                )
            )
        stats.duration_ms = int((time.monotonic() - t0) * 1000)
        if log_totals:
            logger.info(
                f"Search: {search_stats.get('queries_run', 0)} queries, "
                f"{stats.raw_count} ATS URLs, {len(jobs)} records"
            )
        return jobs, stats
