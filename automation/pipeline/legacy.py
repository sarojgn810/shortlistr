"""Helpers for legacy scrapers migrating to unified discovery filter."""

from __future__ import annotations

from models.job import JobRecord
from pipeline.filter import apply_discovery_filter


def filter_to_dicts(jobs: list[JobRecord]) -> list[dict]:
    passed, _, _ = apply_discovery_filter(jobs)
    return [j.to_dict() for j in passed]
