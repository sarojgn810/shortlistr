"""Deterministic intent routing for voice mode.

This is the fast path. ``agent.chat`` runs up to five LLM round-trips per turn,
so anything routed here answers in tens of milliseconds instead of seconds. The
trade is that a wrong match *takes an action* while a miss only costs latency —
so every pattern below is deliberately narrow, and anything conversational is
left to fall through.

Job targeting never comes from speech. Whisper mangles coined names and cannot
say an 8-character id at all, so a job-scoped intent reads the id from the open
offer or the triage cursor, and asks when it has neither.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from voice.wake import normalize

INSTANT = "instant"
SECONDS = "seconds"
MINUTES = "minutes"


@dataclass(frozen=True)
class Intent:
    kind: str                                   # tool | enqueue | nav | triage | clarify | miss
    duration: str = INSTANT
    tool: str | None = None
    args: dict = field(default_factory=dict)
    route: str | None = None
    action: str | None = None
    speech: str | None = None


# Routes mirror dashboard/app/*/page.tsx. "Discover" is the label for /inbox in
# the sidebar, so both words have to land there.
_ROUTES: list[tuple[str, str]] = [
    (r"track(?:er)?|board", "/tracker"),
    (r"connections?", "/connections"),
    (r"settings?", "/settings"),
    (r"reports?|insights?", "/reports"),
    (r"linked\s*in", "/linkedin"),
    (r"resume|cv", "/cv"),
    (r"profile", "/profile"),
    (r"prep", "/prep"),
    (r"pipeline", "/pipeline"),
    (r"apply", "/apply"),
    (r"inbox|discover", "/inbox"),
    (r"dashboard|today|home", "/dashboard"),
]

_NAV_VERB = r"(?:open|go\s+to|show\s+me|take\s+me\s+to|navigate\s+to|switch\s+to|bring\s+up)"

# Duration per tool. Everything here is local except evaluate/explain/prep,
# which wait on an LLM or on Playwright.
_DURATION = {
    "shortlistr.status": INSTANT,
    "shortlistr.list_jobs": INSTANT,
    "shortlistr.whoami": INSTANT,
    "shortlistr.queue_apply": INSTANT,
    "shortlistr.skip": INSTANT,
    "shortlistr.explain": SECONDS,
    "shortlistr.evaluate": SECONDS,
    "shortlistr.prep": SECONDS,
    "shortlistr.apply_assist": SECONDS,
    "shortlistr.resolve_jobs": SECONDS,
}

# Offer options map to the tool that fulfils them. Bare agreement ("yes", "sure",
# "ok") is absent on purpose: an offer names two actions, so agreement picks
# neither and guessing would run a write the user did not choose.
_OFFER_TOOLS = {
    "evaluate": "shortlistr.evaluate",
    "apply": "shortlistr.apply_assist",
    "prep": "shortlistr.prep",
    "explain": "shortlistr.explain",
    "skip": "shortlistr.skip",
    "approve": "shortlistr.queue_apply",
}

_FILLER = re.compile(r"\b(?:umm?|uh+|er|ah|like|please|just|so)\b")

# Job-scoped commands are imperative — "prep this one", "apply to that". A
# question that merely contains the same verb is asking *about* the search, not
# ordering it: "what did I apply to at Acme", "why did you score that so low".
# Without this guard both of those took an action.
_INTERROGATIVE = re.compile(
    r"^(?:why|what|which|when|where|who|how|did|do|does|should|would|could|can|is|are|was|were)\b"
)


def _clean(text: str) -> str:
    """Normalize, then drop filler words. VAD captures thinking noises."""
    return re.sub(r"\s+", " ", _FILLER.sub(" ", normalize(text))).strip()


def _tool(name: str, **args) -> Intent:
    return Intent(kind="tool", tool=name, args=args, duration=_DURATION.get(name, SECONDS))


def _needs_job(name: str, job_id: str | None, what: str) -> Intent:
    if not job_id:
        return Intent(kind="clarify", speech=f"Which job should I {what}?")
    return _tool(name, job_id=job_id)


def _match_offer(text: str, offer: dict) -> Intent | None:
    options = [o for o in (offer.get("options") or []) if o in _OFFER_TOOLS]
    job_id = offer.get("job_id")
    for option in options:
        if re.search(rf"\b{option}\b", text):
            return _tool(_OFFER_TOOLS[option], job_id=job_id)
    if re.fullmatch(r"(?:yes|yeah|yep|sure|ok|okay|please do|go ahead)", text):
        pretty = " or ".join(options) if options else "that"
        return Intent(kind="clarify", speech=f"Sorry — {pretty}?")
    return None


def _match_triage(text: str) -> Intent | None:
    if re.search(r"\bstop (?:telling|announcing|reading)\b|\bbe quiet\b|\bmute\b", text):
        return Intent(kind="triage", action="mute")
    if re.fullmatch(r"(?:start|begin) (?:the )?triage", text):
        return Intent(kind="triage", action="start")
    if re.fullmatch(r"next(?: one)?", text):
        return Intent(kind="triage", action="next")
    if re.fullmatch(r"(?:approve|skip)(?: (?:this|that)(?: one)?)?", text):
        return Intent(kind="triage", action=text.split()[0])
    return None


def _match_tool(text: str, job_id: str | None) -> Intent | None:
    if re.search(r"\bstatus\b", text) or re.fullmatch(r"how am i doing", text):
        return _tool("shortlistr.status")
    if re.search(r"\bwho am i\b|\bmy profile\b", text):
        return _tool("shortlistr.whoami")

    # Question-shaped list reads. Bare "pipeline"/"inbox" stay navigation.
    if re.search(r"\b(?:what'?s?|which|how many|list|any)\b", text):
        if re.search(r"\binbox\b|\bnew jobs?\b", text):
            return _tool("shortlistr.list_jobs", status="inbox")
        if re.search(r"\bpipeline\b|\bevaluated\b", text):
            return _tool("shortlistr.list_jobs", status="evaluated")

    if re.search(r"\b(?:scan|discovery|discover)\b", text) or re.search(
        r"\b(?:find|search for|look for)\b.*\b(?:jobs?|roles?|openings?)\b", text
    ):
        # Never shortlistr.discover: dispatch._discover blocks for minutes and
        # the dashboard client gives up at 90s.
        return Intent(kind="enqueue", tool="discover", duration=MINUTES)

    if _INTERROGATIVE.match(text):
        return None

    if re.search(r"\btell me more\b|\bexplain\b", text):
        return _needs_job("shortlistr.explain", job_id, "explain")
    if re.search(r"\bevaluate\b|\bscore (?:this|that|it)\b", text):
        return _needs_job("shortlistr.evaluate", job_id, "evaluate")
    if re.search(r"\bprep\b|\bcover letter\b", text):
        return _needs_job("shortlistr.prep", job_id, "prep")
    if re.search(r"\bapply\b", text):
        return _needs_job("shortlistr.apply_assist", job_id, "apply to")
    return None


def _route_for(word: str) -> str | None:
    for pattern, route in _ROUTES:
        if re.fullmatch(pattern, word):
            return route
    return None


def _match_nav_explicit(text: str) -> Intent | None:
    """"go to prep" — an explicit verb outranks a job-scoped tool of the same name."""
    stripped = re.sub(rf"^{_NAV_VERB}\s+(?:my |the )?", "", text)
    if stripped == text:
        return None
    route = _route_for(stripped)
    return Intent(kind="nav", route=route) if route else None


def _match_nav_bare(text: str) -> Intent | None:
    """A lone place name — "pipeline", "settings"."""
    route = _route_for(text)
    return Intent(kind="nav", route=route) if route else None


def resolve(text: str, *, offer: dict | None = None, job_id: str | None = None) -> Intent:
    """Route an utterance. Order is precedence: an open offer claims its own answers."""
    cleaned = _clean(text)
    if not cleaned:
        return Intent(kind="miss")

    if offer:
        hit = _match_offer(cleaned, offer)
        if hit:
            return hit
        job_id = job_id or offer.get("job_id")

    matchers = (
        _match_triage,
        _match_nav_explicit,
        lambda t: _match_tool(t, job_id),
        _match_nav_bare,
    )
    for matcher in matchers:
        hit = matcher(cleaned)
        if hit:
            return hit
    return Intent(kind="miss")


# ── Running a resolved intent ─────────────────────────────────────────────────
#
# Everything below dispatches through ``dispatch.call_tool``. Calling a handler
# in ``_BUILTIN_HANDLERS`` directly would be shorter and would route around
# ``check_permission`` — which is exactly what must not happen when the caller
# is a microphone.

def _speak_result(tool: str, result) -> str:
    from voice import speech_form

    if tool == "shortlistr.status":
        return speech_form.status_brief(result if isinstance(result, dict) else {})
    if tool == "shortlistr.list_jobs":
        return speech_form.list_brief(result if isinstance(result, list) else [], "inbox")
    if isinstance(result, dict) and result.get("error"):
        return speech_form.for_speech(f"That didn't work: {result['error']}")
    if tool == "shortlistr.evaluate" and isinstance(result, dict):
        score = result.get("score")
        if score is not None:
            return f"Scored {round(float(score), 1)}. Want me to prep an application?"
    if tool == "shortlistr.prep":
        return "Prep is ready — cover letter and interview guide. Want to look it over?"
    if tool in ("shortlistr.queue_apply", "shortlistr.skip"):
        return "Done. Next one?"
    return speech_form.for_speech(str(result) if result else "Done.")


def run(intent: Intent, *, tenant_id: str = "default") -> dict:
    """Execute a resolved intent, returning a superset of the chat response shape."""
    from voice import speech_form

    base = {"reply": "", "speech": "", "actions": [], "ack": speech_form.waiting_ack(intent.duration)}

    if intent.kind == "miss":
        return {**base, "miss": True}

    if intent.kind == "clarify":
        return {**base, "speech": intent.speech or "Which one?", "reply": intent.speech or ""}

    if intent.kind == "nav":
        return {**base, "nav": intent.route, "speech": "", "reply": f"Opening {intent.route}."}

    if intent.kind == "triage":
        return {**base, "triage": intent.action}

    if intent.kind == "enqueue":
        from store import db

        # Mirrors POST /jobs/discover. enqueue_task already dedupes a discover
        # that is pending or running, so asking twice is harmless.
        db.enqueue_task("discover", {"dry_run": False})
        said = speech_form.waiting_ack(MINUTES)
        return {**base, "speech": f"Starting a scan. {said}", "reply": "Scan queued.",
                "watch": {"kind": "discover"}}

    from agent import dispatch, registry

    try:
        registry.check_permission(intent.tool, confirm=False, tenant_id=tenant_id)
    except registry.PermissionDenied:
        # Submit-class and not on autopilot — surface it, run nothing.
        return {
            **base,
            "speech": "That needs your confirmation. Say confirm, or tap the card.",
            "reply": "Needs confirmation.",
            "pending_confirm": {
                "tool": intent.tool,
                "args": intent.args,
                "prompt": f"Run {intent.tool}?",
            },
        }

    try:
        result = dispatch.call_tool(intent.tool, intent.args, confirm=False, tenant_id=tenant_id)
    except Exception as e:
        return {**base, "speech": speech_form.for_speech(f"That didn't work: {e}"),
                "reply": str(e)}

    said = _speak_result(intent.tool, result)
    return {**base, "speech": said, "reply": said,
            "actions": [{"tool": intent.tool, "result": result}]}


def confirm(tool: str, args: dict | None = None, *, tenant_id: str = "default") -> dict:
    """Run a previously gated submit-class tool after explicit user confirmation."""
    from agent import dispatch

    try:
        result = dispatch.call_tool(tool, args or {}, confirm=True, tenant_id=tenant_id)
    except Exception as e:
        return {"reply": str(e), "speech": f"That didn't work: {e}", "actions": []}
    return {
        "reply": f"Done: {tool}.",
        "speech": "Done. The form is filled in — nothing was submitted.",
        "actions": [{"tool": tool, "result": result}],
    }
