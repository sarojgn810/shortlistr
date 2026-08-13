"""Re-read jobs that were scored before requirements were recorded.

Rescoring from stored evidence covers every evaluation that has a requirement
list. The rest carry a number the model guessed with nothing behind it, so there
is no arithmetic to redo — they have to be read again. That is an LLM call per
job and minutes for a backlog, which is why it goes through the worker queue
instead of a request that would time out.

Each job is queued as its own ``evaluate`` task, reusing the type the worker
already handles. A batch task would be one row to lose: a single bad posting
would fail the whole run, and a restart mid-batch would leave no record of how
far it got.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from store import db as store

logger = logging.getLogger(__name__)

DEFAULT_LIMIT = 200
# Only jobs still waiting on the user. Re-reading one they already ruled on
# spends tokens to change nothing.
_UNDECIDED = ("evaluated", "pending")


def jobs_needing_evidence(limit: int = DEFAULT_LIMIT) -> list[str]:
    """Undecided jobs whose latest evaluation has no requirement list."""
    store.init_db()

    with store.db() as conn:
        placeholders = ",".join("?" for _ in _UNDECIDED)
        rows = conn.execute(
            f"""
            SELECT j.id, (
                     SELECT e.result_json FROM eval_results e
                      WHERE e.job_id = j.id ORDER BY e.id DESC LIMIT 1
                   ) AS latest
              FROM jobs j
              JOIN pipeline p ON p.job_id = j.id
             WHERE p.status IN ({placeholders})
               AND j.archived_at IS NULL
             ORDER BY j.discovered_at DESC
            """,
            _UNDECIDED,
        ).fetchall()

    needing: list[str] = []
    for row in rows:
        if len(needing) >= limit:
            break
        try:
            payload = json.loads(row["latest"] or "{}")
        except Exception:
            payload = {}
        # A job never evaluated at all is a separate concern; this is about
        # evaluations that exist but cannot be ranked.
        if payload and not payload.get("must_haves"):
            needing.append(row["id"])
    return needing


def enqueue_reevaluation(limit: int = DEFAULT_LIMIT) -> dict[str, Any]:
    """Queue a re-evaluation per job. Returns ``{enqueued, job_ids}``."""
    job_ids = jobs_needing_evidence(limit=limit)
    for job_id in job_ids:
        store.enqueue_task("evaluate", {"job_id": job_id})

    if job_ids:
        logger.info("queued %d job(s) for re-evaluation", len(job_ids))
    return {"enqueued": len(job_ids), "job_ids": job_ids}
