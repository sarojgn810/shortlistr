"""Words the speech decoder is told to expect.

Whisper is biased toward ordinary English, so the words that actually decide
routing are the ones it fumbles. Observed on real speech, unprompted:

    "evaluate"          -> "evolve rate", "evil loot", "he value it"
    "pipeline"          -> "eye plane"
    "Accenture DevOps"  -> "Essenture Dilops", "Aksangiad Devab's"
    "Shortlistr"        -> "short list", "shot Lister", "A short list of"

Every one of those fell through to the LLM instead of running the tool the user
asked for. Passing them as hotwords fixes all of them, and does it well enough
that the fast `tiny.en` model matches `base.en` on the same audio — so the
accuracy comes for free rather than costing 200ms a turn.

Company names cannot be enumerated ahead of time, so they are read from the
user's own pipeline: the employers they talk about are, by definition, the ones
already in their job list.
"""

from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)

# Product name, command verbs, and the places you can navigate to — the tokens
# the intent router keys on.
_COMMAND_TERMS = [
    "Shortlistr",
    "evaluate", "approve", "skip", "prep", "discover", "scan", "explain", "triage",
    "status", "pipeline", "inbox", "tracker", "reports", "resume", "profile",
    "connections", "settings", "dashboard",
]

# Role vocabulary that is common in postings and rare in everyday speech.
_DOMAIN_TERMS = ["DevOps", "SRE", "Site Reliability", "Kubernetes", "Terraform", "platform engineer"]

_COMPANY_LIMIT = 40
_CACHE_TTL_SECONDS = 300

_companies: list[str] = []
_fetched_at = 0.0


def _recent_companies() -> list[str]:
    """Employers from the user's own pipeline, cached — this runs per utterance."""
    global _companies, _fetched_at

    if _companies and (time.time() - _fetched_at) < _CACHE_TTL_SECONDS:
        return _companies

    try:
        from store import db

        with db.db() as conn:
            rows = conn.execute(
                "SELECT DISTINCT company FROM jobs "
                "WHERE company IS NOT NULL AND TRIM(company) != '' "
                "ORDER BY rowid DESC LIMIT ?",
                (_COMPANY_LIMIT,),
            ).fetchall()
        _companies = [str(r[0]).strip() for r in rows if r and r[0]]
        _fetched_at = time.time()
    except Exception as e:
        # Recognition degrading slightly beats transcription failing outright.
        logger.debug("could not read companies for voice vocabulary: %s", e)
        _fetched_at = time.time()

    return _companies


def hotwords(include_companies: bool = True) -> str:
    """The bias string handed to the decoder on every utterance."""
    terms = [*_COMMAND_TERMS, *_DOMAIN_TERMS]
    if include_companies:
        terms.extend(_recent_companies())
    return " ".join(terms)


def reset_cache() -> None:
    """Drop the cached company list — used by tests and after a fresh scan."""
    global _companies, _fetched_at
    _companies, _fetched_at = [], 0.0
