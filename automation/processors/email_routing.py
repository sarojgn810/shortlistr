"""
Recruiter email → application status routing (J2.3).

Matches recruiter messages to SQLite applications by company name hints
and advances status: applied → responded, responded → interview.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from store import db as store
from store.status import StatusError, transition_application

logger = logging.getLogger(__name__)

_INTERVIEW_SIGNALS = (
    "interview", "schedule a call", "calendar invite", "meet with",
    "phone screen", "technical round", "hiring manager",
)
_RESPONDED_SIGNALS = (
    "thank you for applying", "received your application", "reviewing your profile",
    "would like to speak", "let's connect", "follow up", "next steps",
    "recruiter", "talent acquisition",
)


def _normalize_company(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower())


def _company_from_sender(sender: str) -> str:
    """Best-effort company from email domain or From header."""
    m = re.search(r"@([a-z0-9.-]+)", sender.lower())
    if not m:
        return ""
    domain = m.group(1)
    base = domain.split(".")[0]
    if base in ("gmail", "yahoo", "outlook", "hotmail", "icloud"):
        return ""
    return base.replace("-", " ").title()


def _company_from_text(text: str) -> str:
    for pat in (
        r"(?:at|@|from|join)\s+([A-Z][A-Za-z0-9&.\- ]{2,40})(?:\s+as|\s+team|\.|,|$)",
        r"opportunity (?:at|with)\s+([A-Z][A-Za-z0-9&.\- ]{2,40})",
    ):
        m = re.search(pat, text)
        if m:
            return m.group(1).strip()
    return ""


def _classify_recruiter_status(subject: str, body: str) -> str | None:
    text = f"{subject} {body}".lower()
    if any(s in text for s in _INTERVIEW_SIGNALS):
        return "interview"
    if any(s in text for s in _RESPONDED_SIGNALS):
        return "responded"
    return None


def _find_application(company_hint: str) -> dict | None:
    if not company_hint:
        return None
    key = _normalize_company(company_hint)
    if len(key) < 3:
        return None
    with store.db() as conn:
        rows = conn.execute(
            """
            SELECT a.id, a.company, a.role, a.status, a.job_id
            FROM applications a
            ORDER BY a.id DESC LIMIT 200
            """
        ).fetchall()
    for row in rows:
        comp = _normalize_company(row["company"] or "")
        if comp and (key in comp or comp in key):
            return dict(row)
    return None


def route_recruiter_message(
    *,
    sender: str,
    subject: str,
    body: str,
    dry_run: bool = False,
) -> dict[str, Any] | None:
    """
    Match one recruiter email to an application and transition status.
    Returns routing result or None if no match.
    """
    new_status = _classify_recruiter_status(subject, body)
    if not new_status:
        return None

    company = _company_from_text(f"{subject} {body}") or _company_from_sender(sender)
    app = _find_application(company)
    if not app:
        return None

    current = (app.get("status") or "evaluated").lower()
    result = {
        "application_id": app["id"],
        "company": app.get("company"),
        "role": app.get("role"),
        "from_status": current,
        "to_status": new_status,
        "matched_company_hint": company,
        "dry_run": dry_run,
    }

    if dry_run:
        result["applied"] = False
        return result

    try:
        if current == "evaluated" and new_status in ("responded", "interview"):
            transition_application(app["id"], "applied", actor="email_routing")
            current = "applied"
        if new_status == "responded" and current == "applied":
            transition_application(app["id"], "responded", actor="email_routing")
        elif new_status == "interview":
            if current == "applied":
                transition_application(app["id"], "responded", actor="email_routing")
            transition_application(app["id"], "interview", actor="email_routing")
        else:
            return None
    except StatusError as e:
        result["error"] = str(e)
        result["applied"] = False
        return result

    result["applied"] = True
    store.audit(
        "email_routing",
        "application",
        str(app["id"]),
        {"from": current, "to": new_status, "sender": sender[:120]},
    )
    return result


def route_from_recruiter_drafts(*, dry_run: bool = False) -> list[dict[str, Any]]:
    """
    Parse data/recruiter_drafts.md entries and route status updates.
    Used when Gmail API unavailable or for batch replay.
    """
    from config import DATA_DIR
    import os

    path = os.path.join(DATA_DIR, "recruiter_drafts.md")
    if not os.path.isfile(path):
        return []

    text = open(path, encoding="utf-8").read()
    blocks = re.split(r"\n---\n", text)
    routed: list[dict[str, Any]] = []
    for block in blocks:
        if "From:" not in block:
            continue
        sender_m = re.search(r"From:\s*(.+)", block)
        subject_m = re.search(r"\*\*Subject:\*\*\s*(.+)", block)
        sender = sender_m.group(1).strip() if sender_m else ""
        subject = subject_m.group(1).strip() if subject_m else ""
        r = route_recruiter_message(
            sender=sender, subject=subject, body=block, dry_run=dry_run
        )
        if r:
            routed.append(r)
    return routed
