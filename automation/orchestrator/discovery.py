"""Discovery orchestrator — fetch → profile gate → persist only keepers."""

from __future__ import annotations

import logging
import time

from models.job import JobRecord
from pipeline.filter import apply_discovery_filter, passes_title_location
from processors.job_filter import score_job
from sources.circuit import record_failure, record_success
from sources.registry import get_registry
from store import db as store
from store.queries import min_fit_threshold

logger = logging.getLogger(__name__)

# Pipeline states that mean the user already acted — never auto-delete these
# when targeting changes, even if the new profile would reject the title.
_PROTECTED_PIPELINE = frozenset({"approved", "submitted"})
_PROTECTED_APPLICATION = frozenset({
    "applied", "responded", "interview", "offer", "rejected",
})


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


def enrich_thin_matching_jobs(*, limit: int = 40) -> dict:
    """Fetch JD text for title-matched stubs (HTTP only — no browser spend)."""
    try:
        from processors.enrich_jd import enrich_stub_jobs

        return enrich_stub_jobs(limit=limit, allow_browser=False, title_match_only=True)
    except Exception as exc:
        logger.warning("JD enrich after discover failed: %s", exc)
        return {"error": str(exc)}


def jobs_for_user_db(
    jobs: list[JobRecord],
    *,
    min_fit: int | None = None,
) -> tuple[list[JobRecord], dict]:
    """Keep only profile-relevant jobs that clear the fit floor.

    Off-target and low-fit rows are dropped here so they never inflate the
    user DB or "Saved so far" counts. Callers may still inspect the rejected
    list from apply_discovery_filter for scan stats.
    """
    threshold = min_fit if min_fit is not None else min_fit_threshold()
    keepers: list[JobRecord] = []
    dropped_off_target = 0
    dropped_low_fit = 0
    for job in jobs:
        relevance = (job.metadata or {}).get("discovery_relevance", "relevant")
        if relevance == "off_target":
            dropped_off_target += 1
            continue
        if not passes_title_location(job):
            dropped_off_target += 1
            continue
        if int(job.fit_score or 0) < threshold:
            dropped_low_fit += 1
            continue
        job.metadata["discovery_relevance"] = "relevant"
        keepers.append(job)
    return keepers, {
        "fetched": len(jobs),
        "kept": len(keepers),
        "dropped_off_target": dropped_off_target,
        "dropped_low_fit": dropped_low_fit,
        "min_fit": threshold,
    }


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
            if stats.error:
                record_failure(name)
                logger.warning(
                    "   %s unhealthy: %s (raw=%s)", name, stats.error, stats.raw_count
                )
            else:
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

    Returns (keepers, rejected_title_location, stats).
    Persistence only writes keepers (relevant + fit floor) — see persist_discovered.
    """
    if not persist_progressively:
        raw, stats = discover_all(log_totals=log_totals)
        passed, rejected, fstats = apply_discovery_filter(raw)
        _tag_relevance(passed, rejected)
        scored = _score_batch(passed)
        keepers, gate = jobs_for_user_db(passed)
        stats["discovery_filter"] = {
            "passed": fstats.passed_discovery,
            "rejected": fstats.rejected_discovery,
            "scored": scored,
        }
        stats["persist_gate"] = {
            **gate,
            "dropped_off_target": gate["dropped_off_target"] + fstats.rejected_discovery,
            "fetched": len(raw),
            "kept": gate["kept"],
        }
        logger.info(
            "Persist gate: fetched=%s title_ok=%s kept=%s dropped_title=%s dropped_fit=%s",
            len(raw),
            len(passed),
            gate["kept"],
            fstats.rejected_discovery,
            gate["dropped_low_fit"],
        )
        return keepers, rejected, stats

    registry = get_registry()
    all_keepers: list[JobRecord] = []
    all_rejected: list[JobRecord] = []
    source_stats: dict = {}
    total_scored = 0
    gate_totals = {
        "fetched": 0,
        "kept": 0,
        "dropped_off_target": 0,
        "dropped_low_fit": 0,
        "min_fit": min_fit_threshold(),
    }

    for adapter in registry.adapters():
        name = adapter.name
        t0 = time.monotonic()
        try:
            jobs, fetch_stats = adapter.fetch_raw(log_totals=log_totals)
            if fetch_stats.error:
                record_failure(name)
                logger.warning(
                    "   %s unhealthy: %s (raw=%s)",
                    name,
                    fetch_stats.error,
                    fetch_stats.raw_count,
                )
            else:
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
        total_scored += _score_batch(passed)
        keepers, gate = jobs_for_user_db(passed)
        gate_totals["fetched"] += len(jobs)
        gate_totals["kept"] += gate["kept"]
        gate_totals["dropped_off_target"] += (
            gate["dropped_off_target"] + fstats.rejected_discovery
        )
        gate_totals["dropped_low_fit"] += gate["dropped_low_fit"]

        n = persist_discovered(keepers)
        logger.info(
            "   %s persisted %s (title_ok=%s dropped_title=%s dropped_fit=%s)",
            name,
            n,
            fstats.passed_discovery,
            fstats.rejected_discovery,
            gate["dropped_low_fit"],
        )
        all_keepers.extend(keepers)
        all_rejected.extend(rejected)

    source_stats["discovery_filter"] = {
        "passed": len(all_keepers),
        "rejected": len(all_rejected),
        "scored": total_scored,
    }
    source_stats["persist_gate"] = gate_totals
    source_stats["jd_enrich"] = enrich_thin_matching_jobs()
    # Jobs whose JD arrived by another path (resolver, eval enricher, a source
    # that ships it inline) keep a title-only score and "JD not fetched yet"
    # forever, because the enrich pass only looks at rows *missing* a JD.
    try:
        from processors.enrich_jd import rescore_fetched_jobs

        source_stats["jd_rescore"] = rescore_fetched_jobs()
    except Exception as exc:
        logger.warning("Fit re-score pass failed: %s", exc)
    try:
        from processors.gmail_verify import verify_pending_gmail_stubs

        source_stats["gmail_verify"] = verify_pending_gmail_stubs(limit=20, allow_browser=False)
    except Exception as exc:
        logger.warning("gmail verify pass failed: %s", exc)
    return all_keepers, all_rejected, source_stats


def purge_mismatched_jobs(limit: int = 5000) -> dict:
    """Re-tag stored jobs against the live profile — never hard-delete.

    Mismatches are marked ``off_target`` (and fit zeroed) so Discover → All
    still shows them; Relevant can hide them. In-flight applications are
    counted as protected for metrics only — they stay tagged, never deleted.
    User discard / skip is the only delete path for Discover jobs.
    """
    import json

    store.init_db()
    threshold = min_fit_threshold()
    off_target = 0
    protected = 0
    with store.db() as conn:
        rows = conn.execute(
            """
            SELECT j.id, j.url, j.title, j.location, j.source, j.salary, j.jd_text,
                   j.fit_score, j.metadata_json,
                   p.status AS pipeline_status,
                   a.status AS application_status
            FROM jobs j
            LEFT JOIN pipeline p ON p.job_id = j.id
            LEFT JOIN applications a ON a.job_id = j.id
            WHERE j.source != 'eval' AND j.archived_at IS NULL
            ORDER BY j.discovered_at DESC, j.updated_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        for row in rows:
            pipe = str(row["pipeline_status"] or "")
            app = str(row["application_status"] or "")
            is_protected = (
                pipe in _PROTECTED_PIPELINE or app in _PROTECTED_APPLICATION
            )

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
            scored = score_job(job.to_dict())
            fit = int(scored.get("fit_score") or 0)
            keep = on_target and fit >= threshold

            try:
                meta = json.loads(row["metadata_json"] or "{}")
            except (TypeError, ValueError):
                meta = {}
            if not isinstance(meta, dict):
                meta = {}
            meta["discovery_relevance"] = "relevant" if keep else "off_target"
            conn.execute(
                "UPDATE jobs SET metadata_json = ?, fit_score = ?, fit_reason = ? WHERE id = ?",
                (
                    json.dumps(meta),
                    fit if keep else 0,
                    str(scored.get("fit_reason") or "") if keep else "",
                    row["id"],
                ),
            )

            if keep:
                continue
            if is_protected:
                protected += 1
            else:
                off_target += 1

    logger.info(
        "Retarget retag: off_target=%s protected=%s min_fit=%s (no deletes)",
        off_target,
        protected,
        threshold,
    )
    # ``purged`` kept as 0 for older callers; ``off_target`` is the real count.
    return {
        "purged": 0,
        "off_target": off_target,
        "protected": protected,
        "min_fit": threshold,
    }


def retag_existing_jobs(limit: int = 5000) -> dict:
    """Re-judge stored jobs; mark mismatches off_target (never delete)."""
    result = purge_mismatched_jobs(limit=limit)
    store.init_db()
    with store.db() as conn:
        remaining = conn.execute(
            """
            SELECT COUNT(*) AS n FROM jobs
            WHERE source != 'eval' AND archived_at IS NULL
            """
        ).fetchone()["n"]
        relevant = conn.execute(
            """
            SELECT COUNT(*) AS n FROM jobs j
            WHERE j.source != 'eval' AND j.archived_at IS NULL
              AND COALESCE(json_extract(j.metadata_json, '$.discovery_relevance'), 'relevant')
                  != 'off_target'
            """
        ).fetchone()["n"]
    out = {
        "updated": remaining,
        "relevant": relevant,
        "purged": 0,
        "off_target": int(result.get("off_target") or 0),
        "protected": result["protected"],
    }
    logger.info(
        "Retarget complete: relevant=%s off_target=%s protected=%s",
        relevant,
        out["off_target"],
        result["protected"],
    )
    return out


def persist_discovered(jobs: list[JobRecord], run_id: str | None = None) -> int:
    """Upsert only profile-relevant, fit-qualified jobs into the user DB."""
    if not jobs:
        return 0
    for j in jobs:
        if "discovery_relevance" not in (j.metadata or {}):
            j.metadata["discovery_relevance"] = (
                "relevant" if passes_title_location(j) else "off_target"
            )
        if (
            not int(j.fit_score or 0)
            and j.metadata.get("discovery_relevance") == "relevant"
        ):
            try:
                scored = score_job(j.to_dict())
                j.fit_score = int(scored.get("fit_score") or 0)
                j.fit_reason = str(scored.get("fit_reason") or "")
            except Exception:
                pass

    keepers, gate = jobs_for_user_db(jobs)
    if gate["dropped_off_target"] or gate["dropped_low_fit"]:
        logger.info(
            "persist_discovered gate: kept=%s dropped_off_target=%s dropped_low_fit=%s",
            gate["kept"],
            gate["dropped_off_target"],
            gate["dropped_low_fit"],
        )
    if not keepers:
        return 0
    try:
        from models.soft_dedupe import collapse_soft_duplicates

        before = len(keepers)
        keepers = collapse_soft_duplicates(keepers)
        if len(keepers) < before:
            logger.info(
                "soft_dedupe: %s → %s (company+title+location)",
                before,
                len(keepers),
            )
    except Exception as exc:
        logger.debug("soft_dedupe skipped: %s", exc)
    n = store.upsert_jobs(keepers)
    store.add_jobs_to_pipeline([j.job_id or j.url for j in keepers])
    if run_id:
        store.audit(
            "jobs_persisted",
            "run",
            run_id,
            {"count": n, **gate},
        )
    return n
