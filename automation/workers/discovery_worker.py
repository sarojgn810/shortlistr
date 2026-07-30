"""Background worker — processes SQLite worker_queue."""

from __future__ import annotations

import json
import logging
from typing import Any

from store import db as store

logger = logging.getLogger(__name__)


def _claim_pending(limit: int = 10) -> list[dict[str, Any]]:
    """Mark pending rows as running and return them.

    Discover tasks are collapsed: keep the newest, cancel older pending duplicates
    so a double-click on Scan does not run two full multi-board scrapes.
    """
    store.init_db()
    claimed: list[dict[str, Any]] = []
    with store.db() as conn:
        # Release rows held by a worker that died, before the "one discover at a
        # time" rule below reads them as live work.
        reaped = store.reap_stale_tasks(conn)
        if reaped:
            logger.warning(
                "Reaped %d task(s) stuck in 'running' for over %d minutes — "
                "the process that claimed them is gone.",
                reaped,
                store.STALE_TASK_MINUTES,
            )

        # Collapse duplicate pending discovers before claiming anything.
        pending_discover = conn.execute(
            """
            SELECT id FROM worker_queue
            WHERE task_type = 'discover' AND status = 'pending'
            ORDER BY id DESC
            """
        ).fetchall()
        if len(pending_discover) > 1:
            keep = pending_discover[0]["id"]
            drop_ids = [r["id"] for r in pending_discover[1:]]
            conn.execute(
                f"""
                UPDATE worker_queue
                SET status = 'cancelled', processed_at = datetime('now')
                WHERE id IN ({",".join("?" * len(drop_ids))})
                """,
                drop_ids,
            )
            logger.info(
                "Cancelled %d duplicate discover task(s); keeping id=%s",
                len(drop_ids),
                keep,
            )

        # Skip a new discover if one is already running.
        running = conn.execute(
            """
            SELECT id FROM worker_queue
            WHERE task_type = 'discover' AND status = 'running'
            LIMIT 1
            """
        ).fetchone()
        if running:
            conn.execute(
                """
                UPDATE worker_queue
                SET status = 'cancelled', processed_at = datetime('now')
                WHERE task_type = 'discover' AND status = 'pending'
                """
            )

        rows = conn.execute(
            """
            SELECT id, task_type, payload_json FROM worker_queue
            WHERE status = 'pending' ORDER BY id LIMIT ?
            """,
            (limit,),
        ).fetchall()
        for row in rows:
            conn.execute(
                "UPDATE worker_queue SET status = 'running', "
                "started_at = datetime('now') WHERE id = ?",
                (row["id"],),
            )
            claimed.append(
                {
                    "id": row["id"],
                    "task_type": row["task_type"],
                    "payload": json.loads(row["payload_json"] or "{}"),
                }
            )
    return claimed


def _finish(task_id: int, *, ok: bool, error: str | None = None) -> None:
    with store.db() as conn:
        if ok:
            conn.execute(
                "UPDATE worker_queue SET status='done', processed_at=datetime('now') WHERE id=?",
                (task_id,),
            )
        else:
            conn.execute(
                "UPDATE worker_queue SET status='failed', attempts=attempts+1, processed_at=datetime('now') WHERE id=?",
                (task_id,),
            )
    if error:
        logger.error("Worker task %s failed: %s", task_id, error)


def _run_discover(payload: dict[str, Any]) -> None:
    from orchestrator.discovery import discover_and_filter

    # Persist after each source so the inbox fills while Apify boards are still
    # running — otherwise a multi-board scan looks empty for several minutes.
    passed, rejected, stats = discover_and_filter(
        log_totals=True,
        persist_progressively=True,
    )
    logger.info(
        "Discover done: relevant=%s off_target=%s sources=%s",
        len(passed),
        len(rejected),
        list(stats.keys()),
    )
    from scheduler.scan_scheduler import record_scan_result

    # A manual scan is still a scan: without this the dashboard keeps reporting
    # the last *scheduled* run and a click looks like it did nothing.
    record_scan_result(stats, added=len(passed))

    from store.settings import get_automation_settings

    settings = get_automation_settings()
    if settings.get("auto_evaluate", True):
        from scheduler.scan_scheduler import auto_evaluate_pending

        approve_threshold = float(settings.get("auto_approve_score") or 0)
        auto_evaluate_pending(limit=25, approve_threshold=approve_threshold)


def _run_evaluate(payload: dict[str, Any]) -> None:
    from api.jobs_api import prepare_job_for_eval
    from eval.service import evaluate_job_text

    job_id = payload.get("job_id", "")
    if job_id:
        with store.db() as conn:
            row = conn.execute(
                "SELECT * FROM jobs WHERE id = ?", (job_id,)
            ).fetchone()
        if row:
            jd, company, role, url = prepare_job_for_eval(dict(row))
            evaluate_job_text(jd, url=url, company=company, role=role, job_id=job_id)
        return
    evaluate_job_text(
        payload.get("jd_text", ""),
        url=payload.get("url", ""),
    )


def process_pending(limit: int = 10) -> int:
    claimed = _claim_pending(limit=limit)
    processed = 0
    for task in claimed:
        task_id = int(task["id"])
        task_type = str(task["task_type"])
        payload = task["payload"] if isinstance(task["payload"], dict) else {}
        try:
            logger.info("Worker starting task %s (%s)", task_id, task_type)
            if task_type == "discover":
                _run_discover(payload)
            elif task_type == "evaluate":
                _run_evaluate(payload)
            elif task_type == "scheduled_scan":
                from scheduler.scan_scheduler import run_scheduled_scan

                run_scheduled_scan(
                    tenant_id=payload.get("tenant_id", "default"),
                    dry_run=bool(payload.get("dry_run")),
                )
            else:
                raise ValueError(f"Unknown task_type: {task_type}")
            _finish(task_id, ok=True)
            processed += 1
        except Exception as e:
            _finish(task_id, ok=False, error=str(e))
    return processed


def main() -> int:
    n = process_pending()
    print(f"Processed {n} worker tasks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
