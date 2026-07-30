"""Match explainer — combine fit_score, fit_reason, and eval results (J1.2)."""

from __future__ import annotations

import json
import re
from typing import Any

from store import db as store
from store.status import validate_job_id

_BULLET_SPLIT = re.compile(r"[\n;•]+|(?<=\.)\s+")


def _bullets_from_text(text: str, *, max_items: int = 5) -> list[str]:
    if not text or not text.strip():
        return []
    parts = [p.strip(" -•\t") for p in _BULLET_SPLIT.split(text.strip()) if p.strip()]
    # Drop very short fragments
    parts = [p for p in parts if len(p) > 12]
    return parts[:max_items]


def _latest_eval(conn, job_id: str) -> dict | None:
    row = conn.execute(
        """
        SELECT score, legitimacy, result_json, created_at
        FROM eval_results WHERE job_id = ?
        ORDER BY id DESC LIMIT 1
        """,
        (job_id,),
    ).fetchone()
    if not row:
        return None
    data = dict(row)
    try:
        data["result"] = json.loads(data.pop("result_json") or "{}")
    except json.JSONDecodeError:
        data["result"] = {}
    return data


def explain_job(job_id: str) -> dict[str, Any]:
    """Build explain JSON for a job (fit + eval + bullets)."""
    jid = validate_job_id(job_id)
    store.init_db()

    with store.db() as conn:
        job = conn.execute("SELECT * FROM jobs WHERE id = ?", (jid,)).fetchone()
        if not job:
            raise ValueError(f"Job not found: {jid}")
        job = dict(job)
        eval_row = _latest_eval(conn, jid)
        pipe = conn.execute(
            "SELECT status, evaluated_at FROM pipeline WHERE job_id = ?", (jid,)
        ).fetchone()

    fit_score = int(job.get("fit_score") or 0)
    fit_reason = str(job.get("fit_reason") or "").strip()
    eval_score = float(eval_row["score"]) if eval_row else None
    legitimacy = (eval_row or {}).get("legitimacy") or "unknown"
    blocks = {}
    if eval_row and eval_row.get("result"):
        blocks = dict(eval_row["result"].get("blocks") or {})

    bullets: list[str] = []
    if blocks.get("B"):
        bullets.extend(_bullets_from_text(str(blocks["B"]), max_items=3))
    if fit_reason:
        bullets.extend(_bullets_from_text(fit_reason, max_items=3))
    if blocks.get("A") and len(bullets) < 5:
        bullets.extend(_bullets_from_text(str(blocks["A"]), max_items=2))

    # Dedupe while preserving order
    seen: set[str] = set()
    unique_bullets: list[str] = []
    for b in bullets:
        key = b.lower()[:80]
        if key not in seen:
            seen.add(key)
            unique_bullets.append(b)
    unique_bullets = unique_bullets[:5]

    primary_score = eval_score if eval_score is not None else round(fit_score / 20.0, 1)

    summary_parts = []
    if eval_score is not None:
        summary_parts.append(f"Eval score {eval_score:.1f}/5")
    if fit_score:
        summary_parts.append(f"discovery fit {fit_score}/100")
    summary_parts.append(f"legitimacy: {legitimacy}")
    summary = " · ".join(summary_parts)

    return {
        "job_id": jid,
        "company": job.get("company"),
        "role": job.get("title"),
        "url": job.get("url"),
        "score": primary_score,
        "eval_score": eval_score,
        "fit_score": fit_score,
        "legitimacy": legitimacy,
        "pipeline_status": dict(pipe)["status"] if pipe else None,
        "bullets": unique_bullets,
        "summary": summary,
        "recommend_apply": eval_score is not None and eval_score >= 4.0,
    }


def explain_job_by_url(url: str) -> dict[str, Any]:
    from models.job import job_id_from_url
    return explain_job(job_id_from_url(url))


def format_explain_text(data: dict[str, Any]) -> str:
    lines = [
        f"{data.get('company', '?')} — {data.get('role', '?')}",
        f"Score: {data.get('score')}/5 · {data.get('summary')}",
        "",
        "Why matched:",
    ]
    for b in data.get("bullets") or []:
        lines.append(f"  • {b}")
    if not data.get("bullets"):
        lines.append("  • (no explainer data — run evaluate first)")
    lines.append(f"\nURL: {data.get('url', '')}")
    return "\n".join(lines)
