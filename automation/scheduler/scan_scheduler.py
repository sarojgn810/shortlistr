"""Scheduled discovery + auto-evaluate pipeline."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from orchestrator.discovery import discover_and_filter, persist_discovered
from store import db as store
from store.settings import get_automation_settings, set_automation_settings

logger = logging.getLogger(__name__)

_BOOT_TIME = time.monotonic()
_BOOT_GRACE_SECONDS = 120


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def record_scan_result(
    stats: dict,
    *,
    added: int = 0,
    tenant_id: str = "default",
) -> None:
    """Stamp scan status so the UI reports the last scan, manual or scheduled.

    ``stats`` is the per-source dict from ``discover_and_filter``. The synthetic
    ``discovery_filter`` entry is not a source and must not be counted.
    """
    source_stats = {
        name: info
        for name, info in stats.items()
        if name != "discovery_filter" and isinstance(info, dict)
    }
    source_errors = {
        name: info.get("error") for name, info in source_stats.items() if info.get("error")
    }
    set_automation_settings(
        {
            "last_scan_at": _utc_now_iso(),
            "last_scan_jobs": added,
            "last_scan_errors": source_errors or None,
            "last_scan_sources_ok": len(source_stats) - len(source_errors),
            "last_scan_sources_total": len(source_stats),
        },
        tenant_id=tenant_id,
    )


def auto_evaluate_pending(*, limit: int = 25, approve_threshold: float = 0) -> tuple[int, int]:
    """Evaluate pending pipeline jobs. Returns (evaluated, auto_approved).

    Uses LLM when configured; otherwise the deterministic heuristic in
    ``evaluate_job_text`` (template mode). Auto-eval must not be skipped just
    because the user has not set an API key — Settings "Score new jobs for me"
    still applies.
    """
    from api.jobs_api import prepare_job_for_eval
    from eval.service import evaluate_job_text
    from store.status import mark_approved

    store.init_db()
    with store.db() as conn:
        rows = conn.execute(
            """
            SELECT j.id FROM pipeline p
            JOIN jobs j ON j.id = p.job_id
            WHERE p.status = 'pending'
            ORDER BY p.added_at DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()

    evaluated = 0
    auto_approved = 0
    for row in rows:
        jid = row["id"]
        try:
            with store.db() as conn:
                job_row = conn.execute("SELECT * FROM jobs WHERE id = ?", (jid,)).fetchone()
            if not job_row:
                continue
            jd, company, role, url = prepare_job_for_eval(dict(job_row))
            result = evaluate_job_text(
                jd, url=url, company=company or "", role=role or "", job_id=jid,
            )
            evaluated += 1
            if approve_threshold > 0 and result.score >= approve_threshold:
                try:
                    mark_approved(jid, actor="scheduler")
                    auto_approved += 1
                except Exception:
                    pass
        except Exception as exc:
            logger.warning("Auto-eval %s: %s", jid, exc)

    return evaluated, auto_approved


def run_scheduled_scan(*, tenant_id: str = "default", dry_run: bool = False) -> dict:
    """
    Discover new jobs, persist to pipeline, optionally auto-evaluate pending jobs.
    Never auto-submits applications.
    """
    settings = get_automation_settings(tenant_id)
    passed, rejected, stats = discover_and_filter(log_totals=True)
    added = 0
    if not dry_run and passed:
        added = persist_discovered(passed)
        try:
            from processors.enrich_jd import enrich_stub_jobs

            stats["jd_enrich"] = enrich_stub_jobs(limit=20, allow_browser=False)
        except Exception as exc:
            logger.warning("JD enrich after scheduled scan failed: %s", exc)
            stats["jd_enrich"] = {"error": str(exc)}

    evaluated = 0
    auto_approved = 0
    min_score = float(settings.get("auto_evaluate_min_score") or 4.0)
    approve_threshold = float(settings.get("auto_approve_score") or 0)

    if not dry_run and settings.get("auto_evaluate", True):
        evaluated, auto_approved = auto_evaluate_pending(
            limit=25, approve_threshold=approve_threshold,
        )

    if not dry_run:
        # Close the loop: distill outcomes into learnings on the scan cadence.
        try:
            from outcomes.reflect import reflect

            reflect(tenant_id=tenant_id)
        except Exception as exc:
            logger.warning("reflect failed: %s", exc)

        outcomes_captured = 0
        try:
            from outcomes.capture import process_inbox

            results = process_inbox(max_messages=50)
            outcomes_captured = len(results)
            if outcomes_captured:
                logger.info("Captured %d outcome(s) from inbox", outcomes_captured)
        except Exception as exc:
            logger.warning("outcome capture failed: %s", exc)

        record_scan_result(stats, added=added, tenant_id=tenant_id)
        store.audit(
            "scheduled_scan",
            "tenant",
            tenant_id,
            {"added": added, "evaluated": evaluated, "auto_approved": auto_approved, "outcomes_captured": outcomes_captured},
        )

    return {
        "discovered": len(passed),
        "rejected": len(rejected),
        "added": added,
        "evaluated": evaluated,
        "auto_approved": auto_approved,
        "outcomes_captured": outcomes_captured if not dry_run else 0,
        "min_score": min_score,
        "dry_run": dry_run,
        "stats": stats,
    }


def scan_is_due(tenant_id: str = "default") -> bool:
    settings = get_automation_settings(tenant_id)
    if not settings.get("scan_enabled"):
        return False
    # Do not scan a fresh clone before the user has a real profile and résumé.
    # The 120s boot grace alone still fired against the field-neutral fallback
    # keywords while onboarding was open.
    from store.settings import effective_onboarding_complete

    done, _ = effective_onboarding_complete(settings)
    if not done:
        return False
    last = settings.get("last_scan_at")
    if not last:
        if time.monotonic() - _BOOT_TIME < _BOOT_GRACE_SECONDS:
            return False
        return True
    try:
        last_dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
    except ValueError:
        return True
    hours = int(settings.get("scan_interval_hours") or 72)
    elapsed = (datetime.now(timezone.utc) - last_dt).total_seconds() / 3600
    return elapsed >= hours


def tick_scheduler(tenant_id: str = "default") -> dict | None:
    """If scan is due, run it. Returns result dict or None if skipped."""
    if not scan_is_due(tenant_id):
        return None
    logger.info("Scheduled scan due — running discovery")
    return run_scheduled_scan(tenant_id=tenant_id)
