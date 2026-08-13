"""Assemble an outreach draft: pick who to write to, then write it.

Three pieces already exist — contact resolution, the relevance guard, and the
evidence-grounded drafter. The ordering matters more than the wiring: a contact
is judged *before* a message is written for them, so an unsuitable one yields a
reason instead of a draft that should never be sent.

Resolution orders people by discovery confidence, which is how loud a profile
is, not how likely they are to be hiring. So the first hit is not taken on
trust: the list is walked until someone plausible appears, and if nobody does,
nothing is drafted.

Nothing here sends. It returns text for the user to read and send themselves.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from store import db as store

logger = logging.getLogger(__name__)


def _resolved(job_id: str) -> dict[str, Any]:
    """Contacts already resolved for this job. Seam for tests."""
    try:
        from store.contact_resolution import get_job_resolution

        return get_job_resolution(job_id) or {"people": [], "emails": []}
    except Exception as e:
        logger.debug("contact resolution lookup failed for %s: %s", job_id, e)
        return {"people": [], "emails": []}


def _job(job_id: str) -> dict[str, Any] | None:
    store.init_db()
    with store.db() as conn:
        row = conn.execute(
            "SELECT id, company, title FROM jobs WHERE id = ?", (job_id,)
        ).fetchone()
    return dict(row) if row else None


def _must_haves(job_id: str) -> list[dict[str, Any]]:
    with store.db() as conn:
        row = conn.execute(
            "SELECT result_json FROM eval_results WHERE job_id = ? ORDER BY id DESC LIMIT 1",
            (job_id,),
        ).fetchone()
    if not row:
        return []
    try:
        return json.loads(row["result_json"] or "{}").get("must_haves") or []
    except Exception:
        return []


def _candidate_name() -> str:
    try:
        from config import CANDIDATE

        return str(CANDIDATE.get("name") or "").strip()
    except Exception:
        return ""


def _signature_name() -> str:
    """The name as a person writes it, not as a résumé typesets it.

    CV extraction keeps whatever the document used, and résumés are routinely
    set in caps — signing an email "SAROJ NAYAK" reads as shouting. Only an
    all-caps name is touched; anything with existing mixed case ("Mary-Jane
    O'Brien", "McDonald") is already how its owner writes it.
    """
    name = _candidate_name()
    if name and name == name.upper():
        return " ".join(part.capitalize() for part in name.split())
    return name


def _best_email(person: dict[str, Any], emails: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Strongest candidate address for this person.

    Addresses link to a person by ``person_id``. An earlier version matched on
    ``full_name``, which the email rows do not carry, so every draft reported
    no address while eight candidates sat in the table.
    """
    person_id = person.get("person_id")
    if person_id is None:
        return None
    mine = [e for e in emails if e.get("person_id") == person_id and e.get("email")]
    if not mine:
        return None
    return max(mine, key=lambda e: float(e.get("final_score") or 0))


def build_outreach(job_id: str) -> dict[str, Any]:
    """Return ``{ok, contact, draft, reason, email}`` for one job. Sends nothing."""
    from prep.contact_relevance import assess_contact
    from prep.outreach_draft import draft_grounded_outreach

    job = _job(job_id)
    if not job:
        return {"ok": False, "draft": "", "reason": "No such job.", "contact": None}

    role = str(job.get("title") or "")
    company = str(job.get("company") or "")
    resolution = _resolved(job_id)
    people = list(resolution.get("people") or [])

    if not people:
        return {
            "ok": False, "draft": "", "contact": None,
            "reason": (
                "No contact has been resolved for this job yet. Run contact "
                "resolution from Prep, or send it by hand."
            ),
        }

    rejected: list[str] = []
    for person in people:
        verdict = assess_contact(person, role=role)
        if not verdict.relevant:
            rejected.append(verdict.reason)
            continue

        draft = draft_grounded_outreach(
            company=company,
            role=role,
            contact_name=str(person.get("full_name") or ""),
            candidate_name=_signature_name(),
            must_haves=_must_haves(job_id),
        )
        best = _best_email(person, list(resolution.get("emails") or []))
        return {
            "ok": True,
            "contact": person,
            "email": str((best or {}).get("email") or ""),
            # Addresses are usually pattern guesses (first.last@, flast@ …).
            # Presenting one as fact invites a bounce, and repeated bounces
            # count against the sender.
            "email_verified": bool(best) and str(best.get("verify_status") or "") == "valid",
            "draft": draft,
            "reason": verdict.reason,
        }

    # Everyone resolved was unsuitable. Say who and why rather than drafting
    # for the least-bad option.
    return {
        "ok": False, "draft": "", "contact": None,
        "reason": rejected[0] if rejected else "No suitable contact for this role.",
    }
