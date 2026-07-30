"""Feed discovered jobs into SQLite pipeline (system of record)."""

from __future__ import annotations

import logging

from models.job import JobRecord, job_id_from_url
from store import db as store
from store.export import export_pipeline

logger = logging.getLogger(__name__)


def feed_jobs(
    jobs: list[JobRecord],
    *,
    dry_run: bool = False,
    export_markdown: bool = True,
) -> int:
    """Upsert jobs and add to pending pipeline. Optionally export pipeline.md."""
    if not jobs:
        return 0

    if dry_run:
        return len(jobs)

    # Batched: two connections total instead of two per job. At 2-hourly ingest
    # the per-job path re-ran the migration ladder thousands of times per tick.
    added = store.upsert_jobs(jobs)
    store.add_jobs_to_pipeline(
        [j.job_id or job_id_from_url(j.url) for j in jobs]
    )

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
