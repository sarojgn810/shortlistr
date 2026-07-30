"""O3 — adapt scoring/eval from outcome learnings. Bounded and transparent.

score_adjustment returns a capped delta plus a human-readable reason, so any
learned change is visible in fit_reason rather than applied silently.
"""

from __future__ import annotations

MAX_DELTA = 15
_GHOST_PENALTY = 8
_CONVERT_BOOST = 6


def _outcome_learnings(tenant_id: str) -> list[dict]:
    try:
        from memory.store import search_learnings

        return [l for l in search_learnings("", limit=200, tenant_id=tenant_id)
                if str(l.get("key", "")).startswith("outcome:")]
    except Exception:
        return []


def score_adjustment(job: dict, tenant_id: str = "default") -> tuple[int, str]:
    """Return (delta, reason) from company/source outcome learnings. Bounded ±MAX_DELTA."""
    company = (job.get("company") or "").strip().lower()
    source = (job.get("source") or "").strip().lower()
    delta = 0
    reasons: list[str] = []

    for learning in _outcome_learnings(tenant_id):
        parts = str(learning.get("key", "")).split(":", 2)
        if len(parts) != 3:
            continue
        _, dim, val = parts
        v = val.strip().lower()
        if (dim == "company" and v == company and company) or (dim == "source" and v == source and source):
            insight = learning.get("insight", "")
            if "deprioritize" in insight:
                delta -= _GHOST_PENALTY
                reasons.append(f"learned: {val} ghosts (−{_GHOST_PENALTY})")
            elif "prioritize" in insight:
                delta += _CONVERT_BOOST
                reasons.append(f"learned: {val} converts (+{_CONVERT_BOOST})")

    delta = max(-MAX_DELTA, min(MAX_DELTA, delta))
    return delta, "; ".join(reasons)


def learnings_prompt_block(tenant_id: str = "default", limit: int = 6) -> str:
    """A short 'what's worked / avoid' block to inject into the eval prompt."""
    learnings = _outcome_learnings(tenant_id)[:limit]
    if not learnings:
        return ""
    lines = "\n".join(f"- {l['insight']}" for l in learnings)
    return f"\n\n--- Signals from past outcomes (weigh these) ---\n{lines}"
