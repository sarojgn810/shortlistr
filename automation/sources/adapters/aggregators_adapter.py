"""Aggregators: Himalayas, Remotive, RemoteOK, WeWorkRemotely, WorkingNomads,
NoDesk, Jobspresso — raw fetch (public boards, no auth)."""

from __future__ import annotations

import logging
import time

from models.job import JobRecord
from scrapers.himalayas_scraper import fetch_himalayas_raw
from scrapers.remotive_scraper import fetch_remotive_raw
from scrapers.remoteok_scraper import fetch_remoteok_raw
from scrapers.weworkremotely_scraper import scrape_weworkremotely
from scrapers.workingnomads_scraper import scrape_workingnomads
from scrapers.nodesk_scraper import scrape_nodesk
from scrapers.jobspresso_scraper import scrape_jobspresso
from sources.base import FetchStats, SourceAdapter

logger = logging.getLogger(__name__)


def _as_records(rows: list[dict]) -> list[JobRecord]:
    """Convert legacy scraper dicts -> JobRecord, skipping rows without a URL."""
    out: list[JobRecord] = []
    for r in rows or []:
        if not (r.get("url") or "").strip():
            continue
        try:
            out.append(JobRecord.from_dict(r))
        except Exception:
            continue
    return out


def _wwr() -> list[JobRecord]:
    return _as_records(scrape_weworkremotely())


def _nomads() -> list[JobRecord]:
    return _as_records(scrape_workingnomads())


def _nodesk() -> list[JobRecord]:
    return _as_records(scrape_nodesk())


def _jobspresso() -> list[JobRecord]:
    return _as_records(scrape_jobspresso())


class AggregatorsAdapter(SourceAdapter):
    name = "aggregators"

    BOARDS = [
        ("Himalayas", fetch_himalayas_raw),
        ("Remotive", fetch_remotive_raw),
        ("RemoteOK", fetch_remoteok_raw),
        ("WeWorkRemotely", _wwr),
        ("WorkingNomads", _nomads),
        ("NoDesk", _nodesk),
        ("Jobspresso", _jobspresso),
    ]

    def fetch_raw(self, log_totals: bool = False) -> tuple[list[JobRecord], FetchStats]:
        """Fetch the seven public boards together.

        These were walked one at a time, which made the source as slow as the sum
        of its worst members: WorkingNomads alone took 7.5s to return 1 job, and
        five of the seven cost 13.5s between them for 4 jobs, while RemoteOK and
        Remotive delivered 134 in 2.5s. Seven different hosts, so running them
        together adds no load on any one of them.
        """
        from sources.parallel import parallel_call

        t0 = time.monotonic()
        stats = FetchStats(source=self.name)

        def _one(label: str, fn):
            def run() -> list[JobRecord]:
                try:
                    raw = fn()
                except Exception as e:
                    logger.warning(f"{label} aggregator failed: {e}")
                    return []
                if log_totals:
                    logger.info(f"{label}: {len(raw)} raw (unfiltered)")
                return raw

            return run

        jobs: list[JobRecord] = []
        for chunk in parallel_call([_one(lbl, fn) for lbl, fn in self.BOARDS]):
            jobs.extend(chunk)
        stats.raw_count = len(jobs)
        stats.duration_ms = int((time.monotonic() - t0) * 1000)
        return jobs, stats
