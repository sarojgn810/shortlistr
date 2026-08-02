"""Prep bundle — cover letter, interview prep, CV PDF, résumé diff."""

from __future__ import annotations

import os
from typing import Any

from prep.diff import compute_diff
from prep.ownership import display_fit, load_owned_prep, owner_key, parse_front_matter
from store import db as store
from store.receipts import create_receipt
from store.status import validate_job_id


def _eval_for_job(conn, job_id: str) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT score, legitimacy, result_json
        FROM eval_results
        WHERE job_id = ?
        ORDER BY id DESC LIMIT 1
        """,
        (job_id,),
    ).fetchone()
    if not row:
        return {}
    d = dict(row)
    return {
        "eval_score": d.get("score"),
        "eval_legitimacy": d.get("legitimacy"),
    }


def _job_dict(row: dict, *, eval_extra: dict | None = None) -> dict:
    extra = eval_extra or {}
    try:
        from config import CANDIDATE

        cand_name = str((CANDIDATE or {}).get("name") or "")
    except Exception:
        cand_name = ""
    jd_full = row.get("jd_text") or ""
    return {
        "url": row.get("url") or "",
        "company": row.get("company") or "",
        "title": row.get("title") or "",
        "jd_snippet": jd_full[:800],
        "jd_text": jd_full,
        "job_id": row.get("id") or "",
        "fit_score": row.get("fit_score") or 0,
        "fit_reason": row.get("fit_reason") or "",
        "eval_score": extra.get("eval_score"),
        "candidate_name": cand_name,
    }


def _find_cv_for_job(job_id: str, company: str) -> str | None:
    """Prefer a PDF named for this job_id; never return another company's random PDF."""
    from apply.ats_strategies import find_cv_pdf

    return find_cv_pdf(company, job_id=job_id)


def get_prep_bundle(job_id: str, *, generate: bool = False) -> dict[str, Any]:
    """Return prep materials for a job. Optionally generate missing artifacts."""
    jid = validate_job_id(job_id)
    store.init_db()

    with store.db() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (jid,)).fetchone()
        if not row:
            raise ValueError(f"Job not found: {jid}")
        job_row = dict(row)
        eval_extra = _eval_for_job(conn, jid)

    job = _job_dict(job_row, eval_extra=eval_extra)
    fit = display_fit({**job_row, **eval_extra, "candidate_name": job["candidate_name"]})
    from api.jobs_api import apply_channel_for

    bundle: dict[str, Any] = {
        "job_id": jid,
        "company": job["company"],
        "role": job["title"],
        "url": job["url"],
        "source": job_row.get("source") or "",
        "apply_channel": apply_channel_for(job_row),
        "candidate_name": fit["candidate_name"] or job["candidate_name"],
        "owner": owner_key(),
        **{k: fit[k] for k in (
            "fit_score", "eval_score", "fit_reason", "fit_label", "fit_primary", "fit_scale"
        )},
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

    prep_path, prep_raw = load_owned_prep(jid, url=job["url"])
    if generate or not prep_path:
        from processors.generate_prep import generate_prep_for_job

        prep_result = generate_prep_for_job(job)
        if prep_result.get("success"):
            prep_path = prep_result.get("path")
            if prep_path and os.path.isfile(prep_path):
                try:
                    prep_raw = open(prep_path, encoding="utf-8").read()
                except OSError:
                    prep_raw = None
        bundle["prep_generated"] = prep_result

    prep_content = None
    if prep_raw:
        _, body = parse_front_matter(prep_raw)
        prep_content = body or prep_raw
    elif prep_path and os.path.isfile(prep_path):
        try:
            raw = open(prep_path, encoding="utf-8").read()
            _, body = parse_front_matter(raw)
            prep_content = body or raw
        except OSError:
            prep_content = None

    bundle["prep_path"] = prep_path
    bundle["prep_content"] = prep_content

    cv_pdf = None
    if generate:
        from processors.generate_cv import generate_cv_for_job

        cv_result = generate_cv_for_job(job)
        if cv_result.get("success"):
            cv_pdf = cv_result.get("path")
        bundle["cv_generated"] = cv_result
    if not cv_pdf:
        cv_pdf = _find_cv_for_job(jid, job["company"])
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

    from prep.reach_out import build_reach_out
    from store.prep_drafts import get_reach_out_saved

    saved_ro = get_reach_out_saved(jid)
    bundle["reach_out"] = build_reach_out(
        job_row,
        user_contacts=saved_ro.get("contacts") or [],
        outreach_draft=saved_ro.get("outreach_draft") or None,
    )

    return bundle


def generate_prep_bundle(job_id: str) -> dict[str, Any]:
    return get_prep_bundle(job_id, generate=True)


def list_prep_summaries(*, limit: int = 100) -> list[dict[str, Any]]:
    """Jobs ready for (or already having) prep materials — one card per role.

    Includes approved / submitted pipeline rows and anything with a saved cover
    draft or a prep receipt, so the Prep page is useful even before the user
    clicks Generate.
    """
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
              j.fit_score,
              j.fit_reason,
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
              ) AS prep_at,
              (
                SELECT e.score FROM eval_results e
                WHERE e.job_id = j.id
                ORDER BY e.id DESC LIMIT 1
              ) AS eval_score
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

    try:
        from config import CANDIDATE

        cand_name = str((CANDIDATE or {}).get("name") or "")
    except Exception:
        cand_name = ""

    items: list[dict[str, Any]] = []
    for row in rows:
        d = dict(row)
        job_id = str(d["job_id"])
        company = str(d.get("company") or "")
        title = str(d.get("title") or "")
        url = str(d.get("url") or "")
        prep_path, _ = load_owned_prep(job_id, url=url)
        has_prep_guide = bool(prep_path and os.path.isfile(prep_path))
        has_cover_draft = bool(get_cover_letter_draft(job_id))
        cv_pdf = _find_cv_for_job(job_id, company) if company else None
        has_cv_pdf = bool(cv_pdf and os.path.isfile(cv_pdf))
        ready = has_prep_guide or has_cover_draft or has_cv_pdf or bool(d.get("prep_at"))
        fit = display_fit({
            "fit_score": d.get("fit_score"),
            "fit_reason": d.get("fit_reason"),
            "eval_score": d.get("eval_score"),
            "candidate_name": cand_name,
        })
        items.append(
            {
                "job_id": job_id,
                "company": company or "Company",
                "role": title or "Role",
                "url": url,
                "location": d.get("location") or "",
                "source": d.get("source") or "",
                "pipeline_status": d.get("pipeline_status") or "",
                "application_status": d.get("application_status") or "",
                "has_prep_guide": has_prep_guide,
                "has_cover_draft": has_cover_draft,
                "has_cv_pdf": has_cv_pdf,
                "ready": ready,
                "updated_at": d.get("prep_at") or d.get("added_at") or "",
                "candidate_name": cand_name,
                "fit_score": fit["fit_score"],
                "eval_score": fit["eval_score"],
                "fit_label": fit["fit_label"],
                "fit_reason": fit["fit_reason"],
            }
        )
    return items
