"""Gmail job-alert ingest — extracts URLs from inbox alerts."""

from __future__ import annotations

import logging
import time

from models.job import JobRecord
from processors.email_monitor import fetch_alert_job_records
from sources.base import FetchStats, SourceAdapter

logger = logging.getLogger(__name__)


class GmailAdapter(SourceAdapter):
    name = "gmail"

    def fetch_raw(self, log_totals: bool = False) -> tuple[list[JobRecord], FetchStats]:
        t0 = time.monotonic()
        stats = FetchStats(source=self.name)
        try:
            jobs = fetch_alert_job_records()
            stats.raw_count = len(jobs)
            if log_totals:
                logger.info(f"Gmail: {len(jobs)} job alert URLs")
        except Exception as e:
            stats.error = str(e)
            logger.warning(f"Gmail adapter failed: {e}")
            jobs = []
        stats.duration_ms = int((time.monotonic() - t0) * 1000)
        return jobs, stats
