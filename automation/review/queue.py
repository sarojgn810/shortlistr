"""Jobs awaiting a decision, best first.

This replaces scanning a list of 385 evaluated jobs that mostly shared a score.
The queue hands back one job at a time in a trustworthy order, with the evidence
that produced its rank, so the decision is "3 of 5 requirements met, these two
missing" rather than "4.5, like everything else".

Only evidence-scored evaluations are ordered. Older evaluations carry a number
the model guessed, and those two measurements do not belong in the same sort:
derived scores top out around 4.6 while guessed ones reach 5.0, so mixing them
would rank the least reliable jobs highest. They are counted and reported
instead, as work still to do.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from eval import scoring
from store import db as store

logger = logging.getLogger(__name__)

DEFAULT_LIMIT = 50
# Statuses that still want a yes/no from the user.
_UNDECIDED = ("evaluated", "pending")


def _latest_evaluations(conn) -> dict[str, dict]:
    """Most recent evaluation per job."""
    rows = conn.execute(
        "SELECT job_id, score, result_json FROM eval_results ORDER BY id ASC"
    ).fetchall()
    latest: dict[str, dict] = {}
    for row in rows:
        try:
            payload = json.loads(row["result_json"] or "{}")
        except Exception:
            continue
        latest[row["job_id"]] = payload
    return latest


def fetch_queue(*, limit: int = DEFAULT_LIMIT) -> dict[str, Any]:
    """Return ``{items, pending_reevaluation, total}`` ordered best first."""
    store.init_db()

    items: list[dict[str, Any]] = []
    pending = 0

    with store.db() as conn:
        placeholders = ",".join("?" for _ in _UNDECIDED)
        jobs = conn.execute(
            f"""
            SELECT j.id, j.company, j.title, j.location, j.url, j.source, p.status
              FROM jobs j
              JOIN pipeline p ON p.job_id = j.id
             WHERE p.status IN ({placeholders})
               AND j.archived_at IS NULL
            """,
            _UNDECIDED,
        ).fetchall()

        evaluations = _latest_evaluations(conn)

    for job in jobs:
        payload = evaluations.get(job["id"])
        if not payload:
            continue

        must_haves = payload.get("must_haves")
        score = scoring.score_from_evidence(must_haves)
        if score is None:
            # Evaluated before requirements were recorded — it has a number, but
            # not one that can be compared with these.
            pending += 1
            continue

        met, total = scoring.evidence_summary(must_haves)
        items.append({
            "job_id": job["id"],
            "company": job["company"] or "",
            "title": job["title"] or "",
            "location": job["location"] or "",
            "url": job["url"] or "",
            "status": job["status"],
            "score": score,
            "met": met,
            "total": total,
            "unmet": scoring.unmet_requirements(must_haves),
            "summary": str(payload.get("summary") or "")[:400],
        })

    # Depth of evidence breaks ties: proving nine requirements beats proving three
    # at the same ratio, and that is the whole reason the score separates at all.
    items.sort(key=lambda i: (-i["score"], -i["total"], i["company"]))

    return {
        "items": items[:limit],
        "pending_reevaluation": pending,
        "total": len(items),
    }
