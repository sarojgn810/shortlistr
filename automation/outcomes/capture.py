"""O1 — capture outcomes from inbound mail and transition application status.

High-confidence signals (rejection / interview invite / offer) auto-transition the
matching application — audited and reversible. Ambiguous mail is left alone (the
existing recruiter-draft path handles it). Outbound actions stay gated by F2.
"""

from __future__ import annotations

import logging

from store import status as st

logger = logging.getLogger(__name__)

# Ordered by precedence; first match wins. (outcome, confidence 1-10, patterns)
_SIGNALS: list[tuple[str, int, tuple[str, ...]]] = [
    ("offer", 9, (
        "pleased to offer", "offer letter", "extend an offer", "compensation package",
        "we are excited to offer",
    )),
    ("rejected", 9, (
        "unfortunately", "not moving forward", "won't be proceeding", "will not be proceeding",
        "decided not to", "other candidates", "position has been filled", "not be moving ahead",
        "regret to inform", "not selected", "pursue other applicants",
    )),
    ("interview", 8, (
        "schedule a call", "schedule an interview", "set up a time", "set up an interview",
        "technical screen", "next steps", "availability for a", "would love to chat",
        "invite you to interview", "book a slot", "hop on a call",
    )),
]


def classify_outcome(subject: str, body: str) -> tuple[str | None, int]:
    """Return (outcome, confidence). (None, 0) when no high-confidence signal matches."""
    text = f"{subject or ''} {body or ''}".lower()
    for outcome, confidence, patterns in _SIGNALS:
        if any(p in text for p in patterns):
            return outcome, confidence
    return None, 0


def match_application(text: str, applications: list[dict] | None = None) -> dict | None:
    """Find the active application whose company name appears in the message text."""
    apps = applications if applications is not None else st.get_active_applications()
    low = (text or "").lower()
    for app in apps:
        company = (app.get("company") or "").strip().lower()
        if company and len(company) >= 3 and company in low:
            return app
    return None


_MARK = {
    "responded": st.mark_responded,
    "interview": st.mark_interview,
    "rejected": st.mark_rejected,
    "offer": st.mark_offer,
}


def apply_outcome(app: dict, outcome: str, *, min_confidence: int = 8, confidence: int = 10,
                  actor: str = "outcome") -> dict | None:
    """Transition the application if confident and the transition is allowed."""
    if confidence < min_confidence or outcome not in _MARK:
        return None
    try:
        return _MARK[outcome](int(app["id"]), actor=actor)
    except st.StatusError as e:  # not a legal transition from current status — skip
        logger.debug("skip %s for app %s: %s", outcome, app.get("id"), e)
        return None


def process_messages(messages: list[dict], *, applications: list[dict] | None = None) -> list[dict]:
    """Core, testable: classify each message, match an application, transition it.

    messages: [{"subject":..., "body":..., "sender":...}]. Returns applied transitions.
    """
    apps = applications if applications is not None else st.get_active_applications()
    results: list[dict] = []
    for msg in messages:
        outcome, conf = classify_outcome(msg.get("subject", ""), msg.get("body", ""))
        if not outcome:
            continue
        text = f"{msg.get('subject','')} {msg.get('body','')} {msg.get('sender','')}"
        app = match_application(text, apps)
        if not app:
            continue
        res = apply_outcome(app, outcome, confidence=conf)
        if res:
            results.append({**res, "company": app.get("company"), "outcome": outcome})
    return results


def process_inbox(max_messages: int = 50) -> list[dict]:
    """Fetch recent inbox messages via Gmail and apply outcomes (best-effort, networked)."""
    try:
        from processors.email_monitor import _decode_body, _get_gmail_service, _get_header

        service = _get_gmail_service()
        if not service:
            return []
        resp = service.users().messages().list(userId="me", maxResults=max_messages).execute()
        messages = []
        for ref in resp.get("messages", []):
            data = service.users().messages().get(userId="me", id=ref["id"]).execute()
            messages.append({
                "sender": _get_header(data, "From"),
                "subject": _get_header(data, "Subject"),
                "body": _decode_body(data),
            })
    except Exception as e:
        logger.warning("inbox fetch failed: %s", e)
        return []
    return process_messages(messages)
