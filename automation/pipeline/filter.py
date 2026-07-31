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


def _location_looks_remote(location: str) -> bool:
    """True when the posting text is a remote/WFH-style location."""
    return any(term in location for term in _cfg._REMOTE_TERMS)


def _hits_location_keywords(location: str, keywords: list[str]) -> bool:
    """Substring match for long place names; word-boundary for short tokens (ist, us)."""
    for lk in keywords:
        if not lk:
            continue
        if len(lk) <= 3:
            if re.search(r"\b" + re.escape(lk) + r"\b", location):
                return True
        elif lk in location:
            return True
    return False


def _geo_keywords() -> list[str]:
    """Place/country anchors from LOCATION_KEYWORDS (excludes bare remote terms)."""
    return [
        kw
        for kw in (_cfg.LOCATION_KEYWORDS or [])
        if kw and kw not in _cfg._REMOTE_TERMS
    ]


def passes_title_location(job: JobRecord) -> bool:
    """Pre-filter: title keywords + location policy (used at discovery stage).

    Reads SEARCH_KEYWORDS and LOCATION_KEYWORDS from config at call time
    (not import time) so profile changes apply without restart.

    Geo-scoped remote: when the user wants Remote *and* named places/countries,
    a remote posting must also mention those places (e.g. Bangalore + Remote →
    Remote India / IST). Bare Remote alone stays worldwide (REMOTE_STRICT).
    """
    if not _title_matches(job.title, _cfg.SEARCH_KEYWORDS):
        return False
    # A user who hasn't stated preferred_locations will take a job anywhere.
    # LOCATION_KEYWORDS falls back to ["remote"] for query building, so gating on
    # it here would reject every posting that carries a city name.
    if not getattr(_cfg, "LOCATION_PREFERENCE_SET", True):
        return True
    location = (job.location or "").lower().strip()
    if not location:
        return True

    geo_kws = _geo_keywords()
    wants_remote = bool(getattr(_cfg, "WANTS_REMOTE", False))
    geo_scoped = bool(wants_remote and geo_kws)
    remote_strict = bool(wants_remote and not geo_kws)

    # Office / hybrid in a preferred city, or remote text that already names
    # the city/country, passes on the geo keywords alone.
    if geo_kws and _hits_location_keywords(location, geo_kws):
        return True

    if _location_looks_remote(location):
        if geo_scoped:
            # Remote but no India/city signal — drop worldwide US/EU remotes.
            return False
        if remote_strict:
            return True
        # Cities only (no Remote in prefs) — reject pure remote.
        return False

    # Concrete foreign city with no preferred hit.
    return False


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
