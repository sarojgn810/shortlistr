"""O2 — reflect application outcomes into durable learnings (F3 memory).

Full recompute each run (clear kind='outcome' then re-derive), so reflection
refines over time without duplicating. Grouped by company, source, and score-band.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

MIN_SAMPLE = 3
_ENGAGED = {"responded", "interview", "offer"}
_COUNTED = ("applied", "responded", "interview", "offer", "rejected")


def _band(score) -> str | None:
    try:
        b = int(float(score))
    except (TypeError, ValueError):
        return None
    return f"{b}.0-{b}.9"


def _reflect_dimension(apps: list[dict], dim: str, key_fn, tenant_id: str, add_learning) -> list[str]:
    groups: dict[str, list[dict]] = {}
    for a in apps:
        k = key_fn(a)
        if k:
            groups.setdefault(str(k), []).append(a)

    written: list[str] = []
    for k, items in groups.items():
        total = len(items)
        if total < MIN_SAMPLE:
            continue
        engaged = sum(1 for a in items if a["status"] in _ENGAGED)
        rate = engaged / total
        conf = min(9, 4 + total)
        if engaged == 0:
            insight = f"{dim} '{k}': 0/{total} responses — deprioritize"
        elif rate >= 0.4:
            insight = f"{dim} '{k}': {engaged}/{total} responses ({int(rate * 100)}%) — prioritize"
        else:
            continue
        add_learning(insight, kind="outcome", key=f"outcome:{dim}:{k}",
                     confidence=conf, source="observed", refs=[], tenant_id=tenant_id)
        written.append(f"outcome:{dim}:{k}")
    return written


def reflect(tenant_id: str = "default") -> list[str]:
    """Recompute outcome learnings from applications. Returns the learning keys written."""
    from memory.store import add_learning, clear_learnings
    from store import db

    db.init_db()
    with db.db() as conn:
        rows = conn.execute(
            "SELECT a.status AS status, a.company AS company, a.score AS score, "
            "j.source AS source FROM applications a "
            "LEFT JOIN jobs j ON j.id = a.job_id "
            f"WHERE a.status IN ({','.join('?' * len(_COUNTED))})",
            _COUNTED,
        ).fetchall()
    apps = [dict(r) for r in rows]

    clear_learnings("outcome", tenant_id)
    written: list[str] = []
    written += _reflect_dimension(apps, "company", lambda a: a.get("company"), tenant_id, add_learning)
    written += _reflect_dimension(apps, "source", lambda a: a.get("source"), tenant_id, add_learning)
    written += _reflect_dimension(apps, "score_band", lambda a: _band(a.get("score")), tenant_id, add_learning)
    logger.info("reflect: wrote %d outcome learnings", len(written))
    return written
