"""Unified discovery + fit filtering pipeline."""

from __future__ import annotations

import re
from dataclasses import dataclass

import config as _cfg
from models.job import JobRecord
from processors.job_filter import filter_jobs, score_job


@dataclass
class FilterStats:
    input_count: int = 0
    passed_discovery: int = 0
    rejected_discovery: int = 0
    passed_fit: int = 0
    rejected_fit: int = 0


def _title_matches(title: str, keywords: list[str]) -> bool:
    """Check if title matches any keyword using word-boundary-aware matching.

    Short keywords (<=4 chars like "SRE") use word-boundary regex to avoid
    substring false positives (e.g. "Rechtsreferendar" matching "SRE").
    Longer keywords use substring matching as before.
    """
    t = title.lower()
    for kw in keywords:
        k = kw.lower()
        if len(k) <= 4:
            if re.search(r'\b' + re.escape(k) + r'\b', t):
                return True
        else:
            if k in t:
                return True
    return False


def passes_title_location(job: JobRecord) -> bool:
    """Pre-filter: title keywords + location policy (used at discovery stage).

    Reads SEARCH_KEYWORDS and LOCATION_KEYWORDS from config at call time
    (not import time) so profile changes apply without restart.
    """
    title_ok = _title_matches(job.title, _cfg.SEARCH_KEYWORDS)
    location = job.location.lower()
    loc_ok = any(lk in location for lk in _cfg.LOCATION_KEYWORDS) or not location.strip()
    if job.source in ("RemoteOK", "Himalayas", "Remotive", "SearchDiscovery"):
        if _cfg.WANTS_REMOTE:
            return title_ok
    return title_ok and loc_ok


def apply_discovery_filter(jobs: list[JobRecord]) -> tuple[list[JobRecord], list[JobRecord], FilterStats]:
    stats = FilterStats(input_count=len(jobs))
    passed, rejected = [], []
    for job in jobs:
        if passes_title_location(job):
            passed.append(job)
            stats.passed_discovery += 1
        else:
            rejected.append(job)
            stats.rejected_discovery += 1
    return passed, rejected, stats


def apply_fit_filter(
    jobs: list[JobRecord], min_score: int | None = None
) -> tuple[list[dict], list[dict], FilterStats]:
    """Fit scoring via existing job_filter; returns legacy dicts for tracker compatibility."""
    dicts = [j.to_dict() for j in jobs]
    strong, weak = filter_jobs(dicts, min_score=min_score)
    stats = FilterStats(
        input_count=len(jobs),
        passed_fit=len(strong),
        rejected_fit=len(weak),
    )
    return strong, weak, stats
