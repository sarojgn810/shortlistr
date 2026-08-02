"""Things the mailbox says need your attention.

A follow-up is not a job and not an application — it is evidence that one exists
and is waiting on you. "Questionnaire still pending from Virtana" means there is
a live application the tracker knows nothing about, because it was made outside
this tool. Nothing here ever invents a job row to hang that on: a fabricated
opening in Discover would be worse than the missing signal.
"""

from __future__ import annotations

import logging
from typing import Any

from store import db as store

logger = logging.getLogger(__name__)

APPLICATION_UPDATE = "application_update"
INVITE_TO_APPLY = "invite_to_apply"


def record_follow_up(
    *,
    kind: str,
    company: str,
    role: str = "",
    subject: str = "",
    sender: str = "",
    source: str = "email",
    job_id: str | None = None,
    application_id: int | None = None,
) -> int | None:
    """Record one open follow-up. Returns its id, or None if it already existed.

    Re-recording an open follow-up for the same company and kind is a no-op —
    the same questionnaire reminder arrives three times a week, and three
    identical rows is nagging rather than tracking. The newest subject is kept,
    so the row always reflects the most recent thing said.
    """
    company = (company or "").strip()
    if not company:
        return None  # without a company there is nothing to act on

    with store.db() as conn:
        existing = conn.execute(
            "SELECT id FROM follow_ups WHERE kind = ? AND company = ? "
            "AND resolved_at IS NULL",
            (kind, company),
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE follow_ups SET subject = ?, sender = ?, "
                "role = COALESCE(NULLIF(?, ''), role) WHERE id = ?",
                (subject, sender, role, existing["id"]),
            )
            return None
        cur = conn.execute(
            "INSERT INTO follow_ups (kind, company, role, subject, sender, source, "
            "job_id, application_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (kind, company, role, subject, sender, source, job_id, application_id),
        )
        new_id = int(cur.lastrowid)

    store.audit("follow_up_recorded", "follow_up", str(new_id),
                {"kind": kind, "company": company, "source": source})
    return new_id


def list_follow_ups(*, include_resolved: bool = False, limit: int = 100) -> list[dict]:
    where = "" if include_resolved else "WHERE resolved_at IS NULL"
    with store.db() as conn:
        rows = conn.execute(
            f"SELECT * FROM follow_ups {where} "
            "ORDER BY resolved_at IS NOT NULL, created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def resolve_follow_up(follow_up_id: int, *, actor: str = "user") -> dict[str, Any]:
    """Mark one done. Reversible via reopen — nothing here deletes."""
    with store.db() as conn:
        row = conn.execute(
            "SELECT id, resolved_at FROM follow_ups WHERE id = ?", (follow_up_id,)
        ).fetchone()
        if not row:
            raise ValueError(f"Follow-up {follow_up_id} not found")
        conn.execute(
            "UPDATE follow_ups SET resolved_at = datetime('now') WHERE id = ?",
            (follow_up_id,),
        )
    store.audit("follow_up_resolved", "follow_up", str(follow_up_id), {"actor": actor})
    return {"id": follow_up_id, "resolved": True}


def reopen_follow_up(follow_up_id: int, *, actor: str = "user") -> dict[str, Any]:
    with store.db() as conn:
        conn.execute(
            "UPDATE follow_ups SET resolved_at = NULL WHERE id = ?", (follow_up_id,)
        )
    store.audit("follow_up_reopened", "follow_up", str(follow_up_id), {"actor": actor})
    return {"id": follow_up_id, "resolved": False}


def open_count() -> int:
    with store.db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM follow_ups WHERE resolved_at IS NULL"
        ).fetchone()
    return int(row["n"] or 0)
