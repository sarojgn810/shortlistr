"""Pipeline and application status machine — J1.1."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from store import db as store
from tracker_tools._common import CANONICAL_STATUSES_LOWER, validate_status

# Pipeline rows (inbox → approve → submit)
PIPELINE_STATUSES = frozenset({"pending", "evaluated", "approved", "skipped", "submitted"})

PIPELINE_TRANSITIONS: dict[str, frozenset[str]] = {
    "pending": frozenset({"evaluated", "skipped"}),
    "evaluated": frozenset({"approved", "skipped", "pending"}),
    "approved": frozenset({"submitted", "skipped", "evaluated"}),
    "skipped": frozenset({"pending"}),
    "submitted": frozenset(),
}

# Application tracker (canonical states.yml ids, lowercase)
APPLICATION_STATUSES = frozenset(CANONICAL_STATUSES_LOWER)

APPLICATION_TRANSITIONS: dict[str, frozenset[str]] = {
    "evaluated": frozenset({"applied", "discarded", "skip"}),
    "applied": frozenset({"responded", "interview", "rejected", "discarded"}),
    "responded": frozenset({"interview", "rejected", "discarded"}),
    "interview": frozenset({"offer", "rejected", "discarded"}),
    "offer": frozenset({"discarded"}),
    "rejected": frozenset(),
    "discarded": frozenset(),
    # skip is reversible: un-skipping a job and reconsidering it must be able to
    # re-enter the active flow (re-evaluate → apply). Without these the pipeline
    # un-skip succeeds but the next upsert (skip → evaluated/applied) 400s.
    "skip": frozenset({"evaluated", "applied"}),
}

_JOB_ID_RE = re.compile(r"^[a-f0-9]{16}$")


class StatusError(ValueError):
    """Invalid status or transition."""


def _normalize_pipeline_status(status: str) -> str:
    s = status.strip().lower()
    if s not in PIPELINE_STATUSES:
        raise StatusError(f"Invalid pipeline status: {status}")
    return s


def _normalize_application_status(status: str) -> str:
    label = validate_status(status)
    s = label.lower()
    if s not in APPLICATION_STATUSES:
        raise StatusError(f"Invalid application status: {status}")
    return s


def validate_job_id(job_id: str) -> str:
    jid = (job_id or "").strip().lower()
    if not _JOB_ID_RE.match(jid):
        raise StatusError("Invalid job_id format")
    return jid


def _assert_pipeline_transition(current: str, new: str) -> None:
    allowed = PIPELINE_TRANSITIONS.get(current, frozenset())
    if new not in allowed:
        raise StatusError(f"Cannot transition pipeline {current!r} → {new!r}")


def _assert_application_transition(current: str, new: str) -> None:
    if current == new:
        return
    allowed = APPLICATION_TRANSITIONS.get(current, frozenset())
    if new not in allowed:
        raise StatusError(f"Cannot transition application {current!r} → {new!r}")


def get_pipeline_row(job_id: str) -> dict | None:
    jid = validate_job_id(job_id)
    with store.db() as conn:
        row = conn.execute(
            "SELECT * FROM pipeline WHERE job_id = ?", (jid,)
        ).fetchone()
    return dict(row) if row else None


def pipeline_status_counts(*, targeted: bool = False) -> dict[str, int]:
    """Pipeline rows grouped by status.

    The raw count answers "what is in the database". `targeted=True` applies the
    same relevance + fit gate as the default job views, so a headline number
    matches the set of jobs the user can actually open — a raw count next to a
    filtered list reads as jobs that have gone missing.
    """
    from store.queries import (
        APPROVED_ONLY,
        NO_EVAL_ARTIFACTS,
        RELEVANT_ONLY,
    )

    if targeted:
        # Exactly the gate api/jobs_api.py uses to build the list, and no more.
        #
        # This used to add MIN_FIT_ONLY, which the list deliberately omits —
        # min-fit is a client-side filter there so a rescored keeper never
        # vanishes from Discover on its own. The count was therefore stricter
        # than the page it was counting: Discover showed 16 pending and Today
        # said 15, and the missing one was a relevant job scoring 20.
        sql = (
            "SELECT p.status, COUNT(*) AS c FROM pipeline p JOIN jobs j ON j.id = p.job_id "
            f"WHERE 1 = 1 {RELEVANT_ONLY} {NO_EVAL_ARTIFACTS} {APPROVED_ONLY} "
            "GROUP BY p.status"
        )
        params: tuple = ()
    else:
        sql = "SELECT status, COUNT(*) AS c FROM pipeline GROUP BY status"
        params = ()

    with store.db() as conn:
        rows = conn.execute(sql, params).fetchall()
    counts = {s: 0 for s in PIPELINE_STATUSES}
    for row in rows:
        counts[str(row["status"])] = int(row["c"])
    return counts


def application_status_counts() -> dict[str, int]:
    with store.db() as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) AS c FROM applications GROUP BY status"
        ).fetchall()
    counts: dict[str, int] = {}
    for row in rows:
        st = (row["status"] or "evaluated").lower()
        counts[st] = counts.get(st, 0) + int(row["c"])
    return counts


def transition_pipeline(
    job_id: str,
    new_status: str,
    *,
    actor: str = "system",
    reason: str = "",
) -> dict:
    """Move a job through the pipeline state machine."""
    jid = validate_job_id(job_id)
    new = _normalize_pipeline_status(new_status)

    with store.db() as conn:
        row = conn.execute(
            "SELECT status FROM pipeline WHERE job_id = ?", (jid,)
        ).fetchone()
        if not row:
            raise StatusError(f"Job {jid} not in pipeline")
        current = str(row["status"])
        _assert_pipeline_transition(current, new)

        evaluated_at = None
        if new == "evaluated":
            evaluated_at = datetime.now(timezone.utc).isoformat()

        conn.execute(
            """
            UPDATE pipeline
            SET status = ?, evaluated_at = COALESCE(?, evaluated_at)
            WHERE job_id = ?
            """,
            (new, evaluated_at, jid),
        )

    store.audit(
        "pipeline_transition",
        "job",
        jid,
        {"from": current, "to": new, "actor": actor, "reason": reason},
    )
    return {"job_id": jid, "from": current, "to": new}


def upsert_application(
    job_id: str,
    *,
    company: str = "",
    role: str = "",
    score: float | None = None,
    status: str = "evaluated",
    applied_date: str | None = None,
    report_path: str = "",
    notes: str = "",
) -> int:
    """Create or update application row for a job."""
    jid = validate_job_id(job_id)
    st = _normalize_application_status(status)

    with store.db() as conn:
        existing = conn.execute(
            "SELECT id, status FROM applications WHERE job_id = ? ORDER BY id DESC LIMIT 1",
            (jid,),
        ).fetchone()

        if existing:
            cur_status = (existing["status"] or "evaluated").lower()
            if cur_status != st:
                _assert_application_transition(cur_status, st)
            conn.execute(
                """
                UPDATE applications SET
                    company = COALESCE(NULLIF(?, ''), company),
                    role = COALESCE(NULLIF(?, ''), role),
                    score = COALESCE(?, score),
                    status = ?,
                    applied_date = COALESCE(?, applied_date),
                    report_path = COALESCE(NULLIF(?, ''), report_path),
                    notes = COALESCE(NULLIF(?, ''), notes)
                WHERE id = ?
                """,
                (company, role, score, st, applied_date, report_path, notes, existing["id"]),
            )
            app_id = int(existing["id"])
        else:
            cur = conn.execute(
                """
                INSERT INTO applications (
                    job_id, company, role, score, status, applied_date, report_path, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (jid, company, role, score, st, applied_date, report_path, notes),
            )
            app_id = int(cur.lastrowid)

    store.audit("application_upsert", "application", str(app_id), {"job_id": jid, "status": st})
    return app_id


def transition_application(app_id: int, new_status: str, *, actor: str = "system") -> dict:
    st = _normalize_application_status(new_status)
    with store.db() as conn:
        row = conn.execute(
            "SELECT id, status, job_id FROM applications WHERE id = ?", (app_id,)
        ).fetchone()
        if not row:
            raise StatusError(f"Application {app_id} not found")
        current = (row["status"] or "evaluated").lower()
        _assert_application_transition(current, st)
        conn.execute(
            "UPDATE applications SET status = ? WHERE id = ?", (st, app_id)
        )
        job_id = row["job_id"]

    store.audit(
        "application_transition",
        "application",
        str(app_id),
        {"from": current, "to": st, "actor": actor, "job_id": job_id},
    )
    return {"application_id": app_id, "from": current, "to": st}


def get_active_applications() -> list[dict]:
    """Applications still in play (for matching inbound outcome signals)."""
    with store.db() as conn:
        rows = conn.execute(
            "SELECT id, job_id, company, role, status FROM applications "
            "WHERE status IN ('applied','responded','interview') ORDER BY id DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def mark_responded(app_id: int, *, actor: str = "outcome") -> dict:
    return transition_application(app_id, "responded", actor=actor)


def mark_interview(app_id: int, *, actor: str = "outcome") -> dict:
    return transition_application(app_id, "interview", actor=actor)


def mark_rejected(app_id: int, *, actor: str = "outcome") -> dict:
    return transition_application(app_id, "rejected", actor=actor)


def mark_offer(app_id: int, *, actor: str = "outcome") -> dict:
    return transition_application(app_id, "offer", actor=actor)


def mark_evaluated(
    job_id: str,
    *,
    company: str = "",
    role: str = "",
    score: float,
    actor: str = "system",
) -> dict[str, Any]:
    """After evaluation: pipeline → evaluated, application row created/updated."""
    jid = validate_job_id(job_id)
    pipe = get_pipeline_row(jid)
    if pipe:
        current = str(pipe["status"])
        if current == "pending":
            transition_pipeline(jid, "evaluated", actor=actor, reason="evaluation_complete")
        elif current == "skipped":
            # Re-evaluating a skipped job is how a user reconsiders it; refusing
            # here left the Re-evaluate button permanently broken for that row.
            transition_pipeline(jid, "pending", actor=actor, reason="reconsider")
            transition_pipeline(jid, "evaluated", actor=actor, reason="evaluation_complete")
        elif current not in ("evaluated", "approved", "submitted"):
            raise StatusError(f"Cannot evaluate job in pipeline state {current!r}")
    else:
        store.add_to_pipeline(jid, "evaluated")

    app_id = upsert_application(
        jid, company=company, role=role, score=score, status="evaluated"
    )
    return {"job_id": jid, "application_id": app_id, "pipeline_status": "evaluated"}


def _walk_pipeline_to(job_id: str, target: str, *, actor: str, reason: str) -> None:
    """Advance a job to `target`, stepping through required intermediate states.

    The user's decision is the event we must honour; the ladder
    (pending → evaluated → approved → submitted) is bookkeeping. Approving
    straight from the inbox used to 400 because `pending → approved` is not a
    legal single hop, and submitting a previously skipped job left the pipeline
    row on `skipped` while the application said `applied` — which dropped the row
    out of the tracker board entirely.
    """
    jid = validate_job_id(job_id)
    # Next legal hop toward the target, per current state. Only forward moves the
    # ladder already allows, plus the skipped → pending un-skip.
    next_hop: dict[str, dict[str, str]] = {
        "approved": {
            "pending": "evaluated",
            "skipped": "pending",
        },
        "submitted": {
            "pending": "evaluated",
            "evaluated": "approved",
            "skipped": "pending",
        },
    }
    for _ in range(6):
        row = get_pipeline_row(jid)
        if not row:
            store.add_to_pipeline(jid, "pending")
            continue
        current = str(row["status"])
        if current == target:
            return
        if target in PIPELINE_TRANSITIONS.get(current, frozenset()):
            transition_pipeline(jid, target, actor=actor, reason=reason)
            return
        hop = next_hop.get(target, {}).get(current)
        if not hop:
            # No legal route (e.g. already submitted) — surface the real error.
            transition_pipeline(jid, target, actor=actor, reason=reason)
            return
        transition_pipeline(jid, hop, actor=actor, reason=f"{reason}:auto")
    raise StatusError(f"Could not move job {jid} to {target!r}")


def mark_approved(job_id: str, *, actor: str = "user") -> dict:
    _walk_pipeline_to(job_id, "approved", actor=actor, reason="user_approved")
    return {"job_id": validate_job_id(job_id), "pipeline_status": "approved"}


def mark_skipped(job_id: str, *, actor: str = "user") -> dict:
    jid = validate_job_id(job_id)
    row = get_pipeline_row(jid)
    if row and str(row["status"]) == "skipped":
        return {"job_id": jid, "pipeline_status": "skipped"}
    transition_pipeline(jid, "skipped", actor=actor, reason="user_skipped")
    upsert_application(jid, status="skip")
    return {"job_id": jid, "pipeline_status": "skipped"}


def mark_submitted(
    job_id: str,
    *,
    company: str = "",
    role: str = "",
    score: float | None = None,
    applied_date: str | None = None,
    actor: str = "system",
) -> int:
    """After assisted submit: pipeline → submitted, application → applied."""
    jid = validate_job_id(job_id)
    pipe = get_pipeline_row(jid)
    if not pipe or str(pipe["status"]) != "submitted":
        _walk_pipeline_to(jid, "submitted", actor=actor, reason="application_sent")

    today = applied_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return upsert_application(
        jid,
        company=company,
        role=role,
        score=score,
        status="applied",
        applied_date=today,
    )
