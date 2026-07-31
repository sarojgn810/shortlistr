"""Feed discovered jobs into SQLite pipeline (system of record)."""

from __future__ import annotations

import logging

from models.job import JobRecord
from store.export import export_pipeline

logger = logging.getLogger(__name__)


def feed_jobs(
    jobs: list[JobRecord],
    *,
    dry_run: bool = False,
    export_markdown: bool = True,
) -> int:
    """Upsert profile-matching jobs and add to pending pipeline.

    Off-target / below-fit rows are dropped (same gate as discovery persist).
    """
    if not jobs:
        return 0

    if dry_run:
        from orchestrator.discovery import jobs_for_user_db
        from pipeline.filter import apply_discovery_filter

        passed, rejected, _ = apply_discovery_filter(jobs)
        for j in passed:
            j.metadata["discovery_relevance"] = "relevant"
        for j in rejected:
            j.metadata["discovery_relevance"] = "off_target"
        keepers, _gate = jobs_for_user_db(passed)
        return len(keepers)

    from orchestrator.discovery import persist_discovered

    added = persist_discovered(jobs)

    if export_markdown and added:
        export_pipeline()
        logger.info(f"Pipeline: {added} jobs → SQLite (+ exported pipeline.md)")

    return added


def feed_from_dicts(
    dicts: list[dict],
    *,
    dry_run: bool = False,
    export_markdown: bool = True,
) -> int:
    eligible = [
        JobRecord.from_dict(d)
        for d in dicts
        if d.get("url") and d.get("source") not in ("LinkedIn",)
    ]
    return feed_jobs(eligible, dry_run=dry_run, export_markdown=export_markdown)
