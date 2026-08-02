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


def _route_application_update(msg: dict, apps: list[dict]) -> dict | None:
    """An application of the user's is waiting on them. Get it in front of them.

    Two shapes, and the second is the common one. If the tracker already knows
    the application, advance it — the employer has engaged, which is what
    'responded' means. If it does not, the user applied outside this tool and
    the tracker has no row at all: a job-centric board cannot show it, so it
    becomes a follow-up. Never a fabricated job row — an invented opening in
    Discover would be worse than the missing signal.
    """
    from processors.email_intent import APPLICATION_UPDATE, classify_intent
    from store import follow_ups

    subject = msg.get("subject", "")
    intent = classify_intent(subject, msg.get("body", ""), msg.get("sender", ""))
    if intent.kind != APPLICATION_UPDATE or not intent.company:
        return None

    text = f"{subject} {msg.get('body','')} {msg.get('sender','')}"
    app = match_application(text, apps)
    transition = apply_outcome(app, "responded", confidence=intent.confidence) if app else None

    follow_ups.record_follow_up(
        kind=APPLICATION_UPDATE,
        company=intent.company,
        subject=subject,
        sender=msg.get("sender", ""),
        application_id=int(app["id"]) if app else None,
        job_id=str(app["job_id"]) if app and app.get("job_id") else None,
    )
    return {
        "company": intent.company,
        "outcome": APPLICATION_UPDATE,
        "follow_up": True,
        **(transition or {}),
    }


def process_messages(messages: list[dict], *, applications: list[dict] | None = None) -> list[dict]:
    """Core, testable: classify each message, match an application, transition it.

    messages: [{"subject":..., "body":..., "sender":...}]. Returns applied transitions.
    """
    apps = applications if applications is not None else st.get_active_applications()
    results: list[dict] = []
    for msg in messages:
        outcome, conf = classify_outcome(msg.get("subject", ""), msg.get("body", ""))
        if not outcome:
            # A terminal outcome outranks "needs action": a rejection settles the
            # application, so there is nothing left to follow up.
            routed = _route_application_update(msg, apps)
            if routed:
                results.append(routed)
            continue
        text = f"{msg.get('subject','')} {msg.get('body','')} {msg.get('sender','')}"
        app = match_application(text, apps)
        if not app:
            continue
        res = apply_outcome(app, outcome, confidence=conf)
        if res:
            results.append({**res, "company": app.get("company"), "outcome": outcome})
    return results


OUTCOME_WINDOW_DAYS = 14


def process_inbox(max_messages: int = 50, *, reader=None) -> list[dict]:
    """Read recent mail and apply rejection / interview / offer outcomes.

    Provider-agnostic: whatever mailbox the user connected. This used to call the
    Gmail API directly, which meant anyone on Outlook, Yahoo or Proton got no
    automatic application tracking at all — and no indication that was the case.

    Deliberately unfiltered by sender: an outcome arrives from the employer or
    their ATS, not from a job board, so there is no useful sender list to narrow
    on. `reader` is injectable for tests, which must never touch a real inbox.
    """
    if reader is None:
        from mail import get_reader

        reader = get_reader()
    if reader is None:
        return []

    try:
        ids = reader.search_recent(days=OUTCOME_WINDOW_DAYS)[:max_messages]
        messages = []
        for msg_id in ids:
            msg = reader.fetch(msg_id)
            if msg is None:
                continue
            messages.append({
                "sender": msg.sender,
                "subject": msg.subject,
                "body": msg.body,
            })
    except Exception as e:
        logger.warning("inbox fetch failed: %s", e)
        return []
    return process_messages(messages)
