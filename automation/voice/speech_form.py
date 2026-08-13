"""Turn tool results into something worth hearing.

A screen and a speaker want opposite things. The dashboard can show an id, a
URL, a score column and forty rows; spoken aloud those are noise, and forty rows
is a monologue the user cannot interrupt. So every formatter here counts rather
than enumerates, drops anything unspeakable, and hands the turn back with a
question.

These are plain templates — free, instant, and structurally unable to read an id
out loud. ``agent.chat`` handles anything that genuinely needs a model.
"""

from __future__ import annotations

import re

_MARKUP = re.compile(r"[*_`#>\[\]()]|https?://\S+")
_SPACES = re.compile(r"\s+")

_ACKS = {
    "instant": "",
    "seconds": "Give me a few seconds.",
    # A scan is 2.5-8.5 minutes. "Just a moment" is a lie the user discovers by
    # waiting, and the whole point of announcing a duration is to be believed.
    "minutes": "That usually takes about five minutes — I'll tell you when it's done.",
}

_PIPELINE_WORDS = {
    "pending": "waiting to be evaluated",
    "evaluated": "evaluated",
    "approved": "approved",
    "submitted": "submitted",
    "skipped": "skipped",
}


def for_speech(text: str) -> str:
    """Strip markdown and URLs — a speaker reads punctuation as noise."""
    return _SPACES.sub(" ", _MARKUP.sub(" ", text or "")).strip()


def waiting_ack(duration: str) -> str:
    return _ACKS.get(duration, "")


def _role(job: dict) -> str:
    company = (job.get("company") or "").strip()
    title = (job.get("title") or "").strip() or "a role"
    if company:
        return f"{company} are hiring {'an' if title[:1].lower() in 'aeiou' else 'a'} {title}"
    return f"There's {'an' if title[:1].lower() in 'aeiou' else 'a'} {title} open"


def job_brief(job: dict, *, offer: str = "Want me to evaluate it, or prep an application?") -> str:
    """Company, title, score, one distinguishing fact — then hand the turn back."""
    parts = [_role(job)]
    location = (job.get("location") or "").strip()
    if location:
        parts.append(f"in {location}")
    said = " ".join(parts) + "."

    score = job.get("score")
    if isinstance(score, (int, float)):
        said += f" Scored {round(float(score), 1)}."
    return for_speech(f"{said} {offer}")


def list_brief(jobs: list[dict], status: str = "inbox") -> str:
    """Count, don't enumerate. Naming forty companies is the failure mode."""
    n = len(jobs or [])
    where = "your inbox" if status == "inbox" else f"the {status} list"
    if not n:
        return for_speech(f"Nothing in {where} right now. Want me to scan for new roles?")
    if n == 1:
        job = jobs[0]
        return job_brief(job)
    top = ", ".join((j.get("company") or "").strip() for j in jobs[:2] if j.get("company"))
    lead = f"{n} in {where}"
    if top:
        lead += f", including {top}"
    return for_speech(f"{lead}. Want me to run through them?")


def status_brief(snapshot: dict) -> str:
    """Speak the pipeline as a sentence, never as a dict."""
    pipeline = snapshot.get("pipeline") or snapshot.get("counts") or {}
    said = [
        f"{count} {_PIPELINE_WORDS.get(key, key)}"
        for key, count in pipeline.items()
        if isinstance(count, int) and count
    ]
    if not said:
        return for_speech("Nothing in the pipeline yet. Want me to scan for roles?")
    if len(said) > 1:
        said[-1] = f"and {said[-1]}"
    return for_speech("You've got " + (", ".join(said) if len(said) > 2 else " ".join(said)) + ".")
