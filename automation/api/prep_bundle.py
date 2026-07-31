"""Prep bundle — cover letter, interview prep, CV PDF, résumé diff."""

from __future__ import annotations

import glob
import os
from typing import Any

from prep.diff import compute_diff
from store import db as store
from store.receipts import create_receipt
from store.status import validate_job_id


def _job_dict(row: dict) -> dict:
    return {
        "url": row.get("url") or "",
        "company": row.get("company") or "",
        "title": row.get("title") or "",
        "jd_snippet": (row.get("jd_text") or "")[:800],
        "job_id": row.get("id") or "",
    }


def _latest_prep_path(company: str, role: str) -> str | None:
    from config import PREP_DIR

    if not os.path.isdir(PREP_DIR):
        return None
    slug_c = (company or "").replace(" ", "_")[:30]
    slug_r = (role or "").replace(" ", "_")[:30]
    pattern = os.path.join(PREP_DIR, f"*{slug_c}*" if slug_c else "*")
    matches = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
    for path in matches:
        if slug_r and slug_r.lower() not in os.path.basename(path).lower():
            continue
        return path
    return matches[0] if matches else None


def get_prep_bundle(job_id: str, *, generate: bool = False) -> dict[str, Any]:
    """Return prep materials for a job. Optionally generate missing artifacts."""
    jid = validate_job_id(job_id)
    store.init_db()

    with store.db() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (jid,)).fetchone()
        if not row:
            raise ValueError(f"Job not found: {jid}")
        job_row = dict(row)

    job = _job_dict(job_row)
    from api.jobs_api import apply_channel_for

    bundle: dict[str, Any] = {
        "job_id": jid,
        "company": job["company"],
        "role": job["title"],
        "url": job["url"],
        "source": job_row.get("source") or "",
        "apply_channel": apply_channel_for(job_row),
    }

    try:
        bundle["diff"] = compute_diff(jid)
    except Exception as exc:
        bundle["diff"] = {"error": str(exc)}

    from processors.cover_letter import generate_cover_letter

    cover = generate_cover_letter(job)
    from store.prep_drafts import get_cover_letter_draft

    draft = get_cover_letter_draft(jid)
    if draft:
        cover = {**cover, "body": draft, "draft_saved": True}
    bundle["cover_letter"] = cover

    prep_path = _latest_prep_path(job["company"], job["title"])
    if generate or not prep_path:
        from processors.generate_prep import generate_prep_for_job

        prep_result = generate_prep_for_job(job)
        if prep_result.get("success"):
            prep_path = prep_result.get("path")
        bundle["prep_generated"] = prep_result
    bundle["prep_path"] = prep_path

    # Surface the guide's contents so the UI can render it inline (not just a path).
    prep_content = None
    if prep_path and os.path.isfile(prep_path):
        try:
            prep_content = open(prep_path, encoding="utf-8").read()
        except Exception:
            prep_content = None
    bundle["prep_content"] = prep_content

    cv_pdf = None
    if generate:
        from processors.generate_cv import generate_cv_for_job

        cv_result = generate_cv_for_job(job)
        if cv_result.get("success"):
            cv_pdf = cv_result.get("path")
        bundle["cv_generated"] = cv_result
    if not cv_pdf:
        from apply.ats_strategies import find_cv_pdf

        cv_pdf = find_cv_pdf(job["company"])
    bundle["cv_pdf_path"] = cv_pdf

    if generate:
        try:
            create_receipt(
                jid,
                "prep",
                cover_letter_text=bundle["cover_letter"].get("body"),
                resume_path=cv_pdf,
                fields={"prep_path": prep_path or ""},
                actor="prep_bundle",
            )
        except Exception:
            pass

    return bundle


def generate_prep_bundle(job_id: str) -> dict[str, Any]:
    return get_prep_bundle(job_id, generate=True)


def list_prep_summaries(*, limit: int = 100) -> list[dict[str, Any]]:
    """Jobs ready for (or already having) prep materials — one card per role.

    Includes approved / submitted pipeline rows and anything with a saved cover
    draft or a prep receipt, so the Prep page is useful even before the user
    clicks Generate.
    """
    from apply.ats_strategies import find_cv_pdf
    from store.prep_drafts import get_cover_letter_draft

    limit = max(1, min(int(limit or 100), 200))
    store.init_db()

    with store.db() as conn:
        rows = conn.execute(
            """
            SELECT
              j.id AS job_id,
              j.company,
              j.title,
              j.url,
              j.location,
              j.source,
              p.status AS pipeline_status,
              p.added_at,
              (
                SELECT a.status FROM applications a
                WHERE a.job_id = j.id
                ORDER BY a.id DESC LIMIT 1
              ) AS application_status,
              (
                SELECT MAX(r.submitted_at) FROM application_receipts r
                WHERE r.job_id = j.id AND r.channel = 'prep'
              ) AS prep_at
            FROM pipeline p
            JOIN jobs j ON j.id = p.job_id
            WHERE p.status IN ('approved', 'submitted')
               OR EXISTS (
                 SELECT 1 FROM application_receipts r
                 WHERE r.job_id = j.id AND r.channel = 'prep'
               )
            ORDER BY
              COALESCE(
                (SELECT MAX(r.submitted_at) FROM application_receipts r
                 WHERE r.job_id = j.id AND r.channel = 'prep'),
                p.added_at
              ) DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    items: list[dict[str, Any]] = []
    for row in rows:
        d = dict(row)
        job_id = str(d["job_id"])
        company = str(d.get("company") or "")
        title = str(d.get("title") or "")
        prep_path = _latest_prep_path(company, title)
        has_prep_guide = bool(prep_path and os.path.isfile(prep_path))
        has_cover_draft = bool(get_cover_letter_draft(job_id))
        cv_pdf = find_cv_pdf(company) if company else None
        has_cv_pdf = bool(cv_pdf and os.path.isfile(cv_pdf))
        ready = has_prep_guide or has_cover_draft or has_cv_pdf or bool(d.get("prep_at"))
        items.append(
            {
                "job_id": job_id,
                "company": company or "Company",
                "role": title or "Role",
                "url": d.get("url") or "",
                "location": d.get("location") or "",
                "source": d.get("source") or "",
                "pipeline_status": d.get("pipeline_status") or "",
                "application_status": d.get("application_status") or "",
                "has_prep_guide": has_prep_guide,
                "has_cover_draft": has_cover_draft,
                "has_cv_pdf": has_cv_pdf,
                "ready": ready,
                "updated_at": d.get("prep_at") or d.get("added_at") or "",
            }
        )
    return items
