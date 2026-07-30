"""LinkedIn signed-out public job listings adapter."""

from __future__ import annotations

import time

from scrapers.linkedin_guest import fetch_linkedin_guest
from sources.base import FetchStats, SourceAdapter


class LinkedInGuestAdapter(SourceAdapter):
    name = "linkedin_guest"

    def fetch_raw(self, log_totals: bool = False):
        stats = FetchStats(source=self.name)
        started = time.monotonic()
        jobs, error = fetch_linkedin_guest()
        stats.raw_count = len(jobs)
        stats.error = error
        stats.duration_ms = int((time.monotonic() - started) * 1000)
        return jobs, stats
