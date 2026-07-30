"""Discovery orchestrator — fetch_all → filter → persist."""

from __future__ import annotations

import logging
import time

from models.job import JobRecord
from pipeline.filter import apply_discovery_filter, passes_title_location
from processors.job_filter import score_job
from sources.circuit import record_failure, record_success
from sources.registry import get_registry
from store import db as store

logger = logging.getLogger(__name__)


def _score_batch(jobs: list[JobRecord]) -> int:
    scored = 0
    for j in jobs:
        try:
            d = score_job(j.to_dict())
            j.fit_score = int(d.get("fit_score", 0))
            j.fit_reason = d.get("fit_reason", "")
            scored += 1
        except Exception:
            pass
    return scored


def _tag_relevance(passed: list[JobRecord], rejected: list[JobRecord]) -> None:
    for j in passed:
        j.metadata["discovery_relevance"] = "relevant"
    for j in rejected:
        j.metadata["discovery_relevance"] = "off_target"


def discover_all(log_totals: bool = False) -> tuple[list[JobRecord], dict]:
    """
    Run all enabled source adapters.
    Returns (all_raw_jobs_unfiltered, source_stats).
    """
    registry = get_registry()
    all_jobs: list[JobRecord] = []
    source_stats: dict = {}

    for adapter in registry.adapters():
        name = adapter.name
        t0 = time.monotonic()
        try:
            jobs, stats = adapter.fetch_raw(log_totals=log_totals)
            record_success(name)
            all_jobs.extend(jobs)
            source_stats[name] = {
                "raw": stats.raw_count,
                "records": len(jobs),
                "duration_ms": stats.duration_ms,
                "error": stats.error,
            }
            logger.info(
                f"   {name}: {stats.raw_count} raw → {len(jobs)} records "
                f"({stats.duration_ms}ms)"
            )
        except Exception as e:
            record_failure(name)
            source_stats[name] = {"raw": 0, "records": 0, "error": str(e)}
            logger.error(f"   {name} failed: {e}")

        elapsed = int((time.monotonic() - t0) * 1000)
        if name in source_stats:
            source_stats[name]["elapsed_ms"] = elapsed

    return all_jobs, source_stats


def discover_and_filter(
    log_totals: bool = False,
    *,
    persist_progressively: bool = False,
) -> tuple[list[JobRecord], list[JobRecord], dict]:
    """Fetch → filter → score.

    When ``persist_progressively`` is True, each source's filtered results are
    written to the DB immediately so the Discover UI fills while slower sources
    (Apify multi-board) are still running.
    """
    if not persist_progressively:
        raw, stats = discover_all(log_totals=log_totals)
        passed, rejected, fstats = apply_discovery_filter(raw)
        _tag_relevance(passed, rejected)
        scored = _score_batch(passed + rejected)
        stats["discovery_filter"] = {
            "passed": fstats.passed_discovery,
            "rejected": fstats.rejected_discovery,
            "scored": scored,
        }
        return passed, rejected, stats

    registry = get_registry()
    all_passed: list[JobRecord] = []
    all_rejected: list[JobRecord] = []
    source_stats: dict = {}
    total_scored = 0

    for adapter in registry.adapters():
        name = adapter.name
        t0 = time.monotonic()
        try:
            jobs, fetch_stats = adapter.fetch_raw(log_totals=log_totals)
            record_success(name)
            source_stats[name] = {
                "raw": fetch_stats.raw_count,
                "records": len(jobs),
                "duration_ms": fetch_stats.duration_ms,
                "error": fetch_stats.error,
            }
            logger.info(
                "   %s: %s raw → %s records (%sms)",
                name,
                fetch_stats.raw_count,
                len(jobs),
                fetch_stats.duration_ms,
            )
        except Exception as e:
            record_failure(name)
            source_stats[name] = {"raw": 0, "records": 0, "error": str(e)}
            logger.error("   %s failed: %s", name, e)
            continue

        elapsed = int((time.monotonic() - t0) * 1000)
        source_stats[name]["elapsed_ms"] = elapsed

        if not jobs:
            continue

        passed, rejected, fstats = apply_discovery_filter(jobs)
        _tag_relevance(passed, rejected)
        total_scored += _score_batch(passed + rejected)
        n = persist_discovered(passed + rejected)
        logger.info(
            "   %s persisted %s (relevant=%s off_target=%s)",
            name,
            n,
            fstats.passed_discovery,
            fstats.rejected_discovery,
        )
        all_passed.extend(passed)
        all_rejected.extend(rejected)

    source_stats["discovery_filter"] = {
        "passed": len(all_passed),
        "rejected": len(all_rejected),
        "scored": total_scored,
    }
    return all_passed, all_rejected, source_stats


def retag_existing_jobs(limit: int = 5000) -> dict:
    """Re-judge already-stored jobs against the current profile targeting.

    Relevance and fit are stamped once, at discovery time. Anything scanned
    before the user finished onboarding therefore keeps the default targeting's
    verdict forever: the rows stay tagged off_target with fit 0, so Discover is
    empty while Settings reports thousands of saved jobs. A targeting change has
    to re-judge what is already in the DB, not just the next scan's results.
    """
    import json

    store.init_db()
    updated = 0
    relevant = 0
    with store.db() as conn:
        rows = conn.execute(
            """
            SELECT id, url, title, location, source, salary, jd_text, metadata_json
            FROM jobs
            WHERE source != 'eval' AND archived_at IS NULL
            ORDER BY discovered_at DESC, updated_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        for row in rows:
            try:
                meta = json.loads(row["metadata_json"] or "{}")
            except (TypeError, ValueError):
                meta = {}
            if not isinstance(meta, dict):
                meta = {}

            job = JobRecord(
                url=row["url"] or "",
                source=row["source"] or "",
                company="",
                title=row["title"] or "",
                location=row["location"] or "",
                jd_text=row["jd_text"] or "",
                salary=row["salary"] or "",
            )
            on_target = passes_title_location(job)
            meta["discovery_relevance"] = "relevant" if on_target else "off_target"
            scored = score_job(job.to_dict())

            # Writes fit_score straight rather than going through upsert_job,
            # whose "0 means not scored by this writer" rule would keep a stale
            # non-zero score alive after the profile stopped matching the job.
            conn.execute(
                "UPDATE jobs SET metadata_json = ?, fit_score = ?, fit_reason = ? WHERE id = ?",
                (
                    json.dumps(meta),
                    int(scored.get("fit_score") or 0),
                    str(scored.get("fit_reason") or ""),
                    row["id"],
                ),
            )
            updated += 1
            relevant += 1 if on_target else 0

    logger.info("Retagged %s stored jobs against current targeting (%s relevant)", updated, relevant)
    return {"updated": updated, "relevant": relevant}


def persist_discovered(jobs: list[JobRecord], run_id: str | None = None) -> int:
    if not jobs:
        return 0
    n = store.upsert_jobs(jobs)
    store.add_jobs_to_pipeline([j.job_id or j.url for j in jobs])
    if run_id:
        store.audit("jobs_persisted", "run", run_id, {"count": n})
    return n
