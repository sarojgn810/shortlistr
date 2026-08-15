"""Scheduling approved applications, with a window to take it back.

Submission is the one irreversible thing this tool does, so it is deliberately
not immediate. Scheduling puts a row on the worker queue carrying the time it
becomes eligible; cancelling deletes that row. Between the two the user can
change their mind, which is the whole point.

The deadline lives in the queued row rather than only in a timer thread,
because the process holding the timer can die. Whatever picks the row up
afterwards re-checks the clock and the preconditions, and **fails closed**: a
dropped submission costs one click to retry, while one that fires inside its own
undo window cannot be retrieved.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any

from apply import submit as submit_mod
from store import db as store

logger = logging.getLogger(__name__)

TASK_TYPE = "auto_apply"
DEFAULT_DELAY_SECONDS = 60


class TooEarly(RuntimeError):
    """The undo window has not elapsed. Never send; let the row fail."""


class NotSendable(RuntimeError):
    """Preconditions no longer hold at send time."""


def _pending_rows() -> list[dict[str, Any]]:
    with store.db() as conn:
        rows = conn.execute(
            "SELECT id, payload_json FROM worker_queue "
            "WHERE task_type = ? AND status = 'pending' ORDER BY id",
            (TASK_TYPE,),
        ).fetchall()
    out = []
    for row in rows:
        try:
            payload = json.loads(row["payload_json"] or "{}")
        except Exception:
            continue
        out.append({"id": row["id"], **payload})
    return out


def pending_submissions() -> list[dict[str, Any]]:
    """Queued submissions with time remaining — what the countdown renders."""
    now = time.time()
    return [
        {
            "job_id": row.get("job_id", ""),
            "submit_after": row.get("submit_after", 0),
            "seconds_left": max(0, int(row.get("submit_after", 0) - now)),
        }
        for row in _pending_rows()
    ]


def schedule_submission(
    job_id: str,
    *,
    delay_seconds: int = DEFAULT_DELAY_SECONDS,
    start_timer: bool = True,
) -> dict[str, Any]:
    """Queue an approved job for submission after the undo window."""
    store.init_db()

    check = submit_mod.check_preconditions(job_id)
    if not check["ok"]:
        return {"scheduled": False, "reason": check["reason"]}

    # Two rows for one posting means two applications to the same company.
    if any(row.get("job_id") == job_id for row in _pending_rows()):
        existing = next(p for p in pending_submissions() if p["job_id"] == job_id)
        return {"scheduled": True, "reason": "already queued", **existing}

    submit_after = time.time() + max(0, delay_seconds)
    with store.db() as conn:
        conn.execute(
            "INSERT INTO worker_queue (task_type, payload_json) VALUES (?, ?)",
            (TASK_TYPE, json.dumps({"job_id": job_id, "submit_after": submit_after})),
        )
    store.audit("submission_scheduled", "job", job_id, {"submit_after": submit_after})

    if start_timer:
        _arm_timer(delay_seconds)

    return {"scheduled": True, "reason": "", "job_id": job_id, "submit_after": submit_after,
            "seconds_left": max(0, int(delay_seconds))}


def cancel_submission(job_id: str) -> dict[str, Any]:
    """Delete the queued row, if it has not been claimed yet."""
    store.init_db()
    with store.db() as conn:
        cur = conn.execute(
            "DELETE FROM worker_queue WHERE task_type = ? AND status = 'pending' "
            "AND payload_json LIKE ?",
            (TASK_TYPE, f'%"{job_id}"%'),
        )
        removed = cur.rowcount or 0
    if removed:
        store.audit("submission_cancelled", "job", job_id, {})
    return {"cancelled": bool(removed)}


def _arm_timer(delay_seconds: int) -> None:
    """Wake the worker once the window closes. A daemon thread, so best-effort.

    Losing it is survivable: the row stays pending and any later worker pass
    picks it up, at which point the deadline in the payload has passed anyway.
    """

    def fire() -> None:
        try:
            from workers.discovery_worker import process_pending

            process_pending()
        except Exception as e:
            logger.warning("auto-apply timer failed: %s", e)

    threading.Timer(max(1, delay_seconds) + 1, fire).start()


def _send(job_id: str, *, headless: bool = True) -> dict[str, Any]:
    """Actually submit. Isolated so the guards above can be tested without a browser."""
    return submit_mod.submit_application(job_id, headless=headless)


def run_scheduled_submission(payload: dict[str, Any]) -> dict[str, Any]:
    """Worker entry point. Raises rather than sending when anything is off."""
    job_id = str(payload.get("job_id") or "")
    submit_after = float(payload.get("submit_after") or 0)

    if time.time() < submit_after:
        # A restart must not turn "queued a moment ago" into "send it now".
        raise TooEarly(
            f"{job_id} is still inside its undo window "
            f"({int(submit_after - time.time())}s left)"
        )

    # The state at scheduling time is not the state at sending time: approval
    # may have been withdrawn, or the CV deleted, while the window ran.
    check = submit_mod.check_preconditions(job_id)
    if not check["ok"]:
        raise NotSendable(f"{job_id}: {check['reason']}")

    logger.info("auto-apply sending %s", job_id)
    return _send(job_id)
