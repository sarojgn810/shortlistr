"""Pipeline URL resolver adapter."""

from __future__ import annotations

import logging
import time

from models.job import JobRecord
from processors.pipeline_resolver import resolve_pending_ats_jobs
from sources.base import FetchStats, SourceAdapter

logger = logging.getLogger(__name__)


class UrlResolverAdapter(SourceAdapter):
    name = "url_resolver"

    def fetch_raw(self, log_totals: bool = False) -> tuple[list[JobRecord], FetchStats]:
        t0 = time.monotonic()
        stats = FetchStats(source=self.name)
        resolved = resolve_pending_ats_jobs()
        stats.raw_count = len(resolved)
        jobs = [JobRecord.from_dict(d) for d in resolved]
        stats.duration_ms = int((time.monotonic() - t0) * 1000)
        if log_totals:
            logger.info(f"URL resolver: {len(jobs)} pipeline ATS jobs")
        return jobs, stats
