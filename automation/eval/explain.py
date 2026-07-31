"""Match explainer — combine fit_score, fit_reason, and eval results (J1.2)."""

from __future__ import annotations

import json
import re
from typing import Any

from store import db as store
from store.status import validate_job_id

_BULLET_SPLIT = re.compile(r"[\n;•]+|(?<=\.)\s+")

# Discovery fit_reason often dumps scorer tokens that are noise in the drawer.
_NOISE_BULLET = re.compile(
    r"^(?:"
    r"jd not fetched yet|"
    r"preferred location|"
    r"title match|"
    r"location match|"
    r"remote ok|"
    r"keyword match|"
    r"fit score|"
    r"unknown"
    r")\.?$",
    re.I,
)


def _bullets_from_text(text: str, *, max_items: int = 5) -> list[str]:
    if not text or not text.strip():
        return []
    parts = [p.strip(" -•\t") for p in _BULLET_SPLIT.split(text.strip()) if p.strip()]
    parts = [p for p in parts if len(p) > 12 and not _NOISE_BULLET.match(p)]
    return parts[:max_items]


def _is_useful_bullet(text: str) -> bool:
    t = (text or "").strip()
    if len(t) < 16:
        return False
    if _NOISE_BULLET.match(t):
        return False
    return True


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
        try:
            from writing.sanitize import sanitize_blocks

            blocks = sanitize_blocks(blocks, mode="prose")
        except Exception:
            pass

    bullets: list[str] = []
    if blocks.get("B"):
        bullets.extend(_bullets_from_text(str(blocks["B"]), max_items=3))
    if fit_reason:
        bullets.extend(_bullets_from_text(fit_reason, max_items=3))
    if blocks.get("A") and len(bullets) < 5:
        bullets.extend(_bullets_from_text(str(blocks["A"]), max_items=2))
    if blocks.get("D") and len(bullets) < 5:
        bullets.extend(_bullets_from_text(str(blocks["D"]), max_items=1))

    # Concrete fallbacks when discovery left only scorer tokens.
    if not bullets:
        company = (job.get("company") or "").strip()
        title = (job.get("title") or "").strip()
        location = (job.get("location") or "").strip()
        if title and company:
            bullets.append(f"Title matches your search: {title} at {company}.")
        elif title:
            bullets.append(f"Title matches your search: {title}.")
        if location:
            bullets.append(f"Location: {location}.")
        if fit_score > 0:
            bullets.append(f"Discovery fit {fit_score}/100 — run Evaluate for a full A–G score.")
        if not (job.get("jd_text") or "").strip():
            bullets.append("Job description not loaded yet — Evaluate fetches the posting text.")

    # Dedupe while preserving order
    seen: set[str] = set()
    unique_bullets: list[str] = []
    for b in bullets:
        if not _is_useful_bullet(b) and "Discovery fit" not in b and "not loaded" not in b:
            # Keep our explicit fallbacks even if short-ish.
            if not b.startswith("Title matches") and not b.startswith("Location:"):
                continue
        key = b.lower()[:80]
        if key not in seen:
            seen.add(key)
            unique_bullets.append(b)
    unique_bullets = unique_bullets[:5]
    try:
        from writing.sanitize import sanitize

        unique_bullets = [sanitize(b, mode="prose") for b in unique_bullets]
    except Exception:
        pass

    primary_score = eval_score if eval_score is not None else (
        round(fit_score / 20.0, 1) if fit_score > 0 else 0.0
    )

    summary_parts = []
    if eval_score is not None:
        summary_parts.append(f"Eval score {eval_score:.1f}/5")
    if fit_score:
        summary_parts.append(f"discovery fit {fit_score}/100")
    summary_parts.append(f"legitimacy: {legitimacy}")
    if not (job.get("jd_text") or "").strip() and eval_score is None:
        summary_parts.append("JD not loaded — Evaluate to fetch")
    summary = " · ".join(summary_parts)
    try:
        from writing.sanitize import sanitize

        summary = sanitize(summary, mode="label")
    except Exception:
        pass

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
        "has_jd": bool((job.get("jd_text") or "").strip()),
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
    text = "\n".join(lines)
    try:
        from writing.sanitize import sanitize

        return sanitize(text, mode="label")
    except Exception:
        return text
