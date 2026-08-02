"""Background worker — processes SQLite worker_queue."""

from __future__ import annotations

import json
import logging
import threading
from contextlib import contextmanager
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
            # Stamp the first heartbeat with the claim itself. Without it a task
            # would look stale the instant it was claimed.
            conn.execute(
                "UPDATE worker_queue SET status = 'running', "
                "started_at = datetime('now'), heartbeat_at = datetime('now'), "
                "owner = ? WHERE id = ?",
                (store.WORKER_ID, row["id"]),
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
    from store import db as store

    # Every scan the user actually triggers arrives here — the dashboard calls
    # /jobs/discover with async_run=true, which enqueues rather than running
    # inline. Only the synchronous branch recorded a run, so the runs table held
    # nothing but hand-made API calls, and jobs_strong_fit was never written for
    # a real scan at all.
    run_id = store.start_run(dry_run=bool(payload.get("dry_run")))

    # Persist after each source so the inbox fills while Apify boards are still
    # running — otherwise a multi-board scan looks empty for several minutes.
    passed, rejected, stats = discover_and_filter(
        log_totals=True,
        persist_progressively=True,
    )
    gate = stats.get("persist_gate") or {}
    try:
        from processors.job_filter import count_strong_fit_persisted

        strong = count_strong_fit_persisted(passed)
    except Exception as exc:
        logger.warning("strong-fit count failed: %s", exc)
        strong = 0
    store.finish_run(
        run_id,
        source_stats=stats,
        discovered=int(gate.get("fetched") or (len(passed) + len(rejected))),
        passed=len(passed),
        strong_fit=strong,
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


@contextmanager
def _heartbeating(task_id: int):
    """Prove this worker is alive for as long as the task runs.

    A scan is one long synchronous call, so the beat needs its own thread. It is
    a daemon on purpose: if the process is killed the thread dies with it, the
    beat stops, and reap_stale_tasks frees the row about a minute later. That is
    the whole point — silence is the signal.
    """
    stop = threading.Event()

    def _beat() -> None:
        while not stop.wait(store.HEARTBEAT_SECONDS):
            try:
                store.touch_task_heartbeat(task_id)
            except Exception as exc:  # a missed beat must never kill the task
                logger.debug("Heartbeat for task %s failed: %s", task_id, exc)

    t = threading.Thread(target=_beat, daemon=True, name=f"heartbeat-{task_id}")
    t.start()
    try:
        yield
    finally:
        stop.set()


def process_pending(limit: int = 10) -> int:
    claimed = _claim_pending(limit=limit)
    processed = 0
    for task in claimed:
        task_id = int(task["id"])
        task_type = str(task["task_type"])
        payload = task["payload"] if isinstance(task["payload"], dict) else {}
        try:
            logger.info("Worker starting task %s (%s)", task_id, task_type)
            with _heartbeating(task_id):
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
