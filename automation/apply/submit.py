"""Sending an application the user already approved.

``ats_fill`` deliberately stops before Submit, because until now a human was
always at the keyboard to look at the filled form and decide. Auto-apply removes
that person from the moment of sending, so everything they used to check by
looking has to become an assertion here.

Two lines hold:

**Approval is the gate, and only a human passes it.** Nothing in this module
approves anything. It acts on jobs already marked ``approved`` and refuses every
other state — ``evaluated`` most of all, since that means the machine formed an
opinion and nobody agreed with it yet.

**A blank application is worse than none.** Submitting a form full of defaults
does not just fail; it burns that company for this candidate permanently. So a
tailored CV and a cover letter must both exist before anything is sent.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

from store import db as store

logger = logging.getLogger(__name__)


def _cv_pdf_for(job_id: str) -> str | None:
    """The tailored CV PDF for this job, if one has been generated."""
    try:
        from api.prep_bundle import _find_cv_for_job

        with store.db() as conn:
            row = conn.execute("SELECT company FROM jobs WHERE id = ?", (job_id,)).fetchone()
        path = _find_cv_for_job(job_id, row["company"] if row else "")
        return path if path and os.path.exists(path) else None
    except Exception as e:
        logger.debug("cv lookup failed for %s: %s", job_id, e)
        return None


def _cover_letter_for(job_id: str) -> str:
    """The saved cover letter draft for this job."""
    try:
        from store.prep_drafts import get_cover_letter_draft

        return (get_cover_letter_draft(job_id) or "").strip()
    except Exception as e:
        logger.debug("cover letter lookup failed for %s: %s", job_id, e)
        return ""


def check_preconditions(job_id: str) -> dict[str, Any]:
    """Everything that must be true before sending. ``{ok, reason, ...}``.

    ``reason`` is shown beside a job that did not go out, so it has to say what
    to do about it — "not ready" would leave the user with nowhere to go.
    """
    from store.status import get_pipeline_row

    try:
        pipe = get_pipeline_row(job_id)
    except Exception:
        pipe = None

    status = (pipe or {})["status"] if pipe else None
    if status != "approved":
        return {
            "ok": False,
            "status": status,
            "reason": (
                f"Only approved jobs are sent automatically (this one is "
                f"{status or 'not in the pipeline'}). Approve it in Review first."
            ),
        }

    with store.db() as conn:
        row = conn.execute(
            "SELECT url, source, company, metadata_json FROM jobs WHERE id = ?", (job_id,)
        ).fetchone()
    if not row or not (row["url"] or "").strip():
        return {"ok": False, "status": status,
                "reason": "This job has no application URL to submit to."}

    from apply.channels import application_url, is_link_only

    # Prefer the employer's own application link over the aggregator listing —
    # a LinkedIn job view has no form on it.
    if is_link_only(application_url(row), str(row["source"] or "")):
        return {
            "ok": False,
            "status": status,
            "reason": (
                "This posting only links out — there is no form to fill, so it "
                "has to be applied to by hand."
            ),
        }

    if not _cv_pdf_for(job_id):
        return {
            "ok": False,
            "status": status,
            "reason": (
                "No tailored CV has been generated for this job. Open Prep and "
                "generate one before it can be sent."
            ),
        }

    if not _cover_letter_for(job_id):
        return {
            "ok": False,
            "status": status,
            "reason": (
                "No cover letter has been written for this job. Open Prep and "
                "generate one before it can be sent."
            ),
        }

    return {"ok": True, "status": status, "reason": ""}


def _screenshot_path(job_id: str) -> str:
    from config import SHORTLISTR_ROOT

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    folder = os.path.join(SHORTLISTR_ROOT, "output", "submissions")
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, f"{job_id}-{stamp}.png")


def _record_artifact(job_id: str, path: str) -> None:
    """Keep the screenshot against the job — it is the only record of what was sent."""
    try:
        with store.db() as conn:
            conn.execute(
                "INSERT INTO artifacts (path, kind, job_ref) VALUES (?, ?, ?)",
                (path, "submission_screenshot", job_id),
            )
    except Exception as e:
        logger.warning("could not record submission screenshot for %s: %s", job_id, e)


def submit_application(job_id: str, *, headless: bool = True) -> dict[str, Any]:
    """Fill the form, photograph it, send it, and record what happened.

    The screenshot is taken **before** the click, not after. After the click the
    page is a confirmation screen or an error, neither of which shows what was
    actually entered — and what was entered is the thing there is otherwise no
    record of.
    """
    check = check_preconditions(job_id)
    if not check["ok"]:
        return {"ok": False, "submitted": False, "reason": check["reason"]}

    from apply.ats_fill import apply_assist_for_job

    # One fill implementation, shared with the manual assist path, so the two
    # cannot drift into filling forms differently. The submit happens inside
    # that same browser session — there is no second visit.
    shot = _screenshot_path(job_id)
    report = apply_assist_for_job(
        job_id, headless=headless, submit=True, screenshot_path=shot
    )

    result: dict[str, Any] = {
        "ok": bool(report.get("submitted")),
        "submitted": bool(report.get("submitted")),
        "job_id": job_id,
        "screenshot": report.get("screenshot"),
        "filled": report.get("filled", []),
        "unfilled": report.get("unfilled", []),
        "reason": "",
    }

    if result["screenshot"]:
        _record_artifact(job_id, result["screenshot"])

    if not result["submitted"]:
        result["reason"] = (
            "; ".join(report.get("errors") or [])
            or "No submit control was reachable on the filled form. It is filled "
               "in and waiting — send it from Apply."
        )
        return result

    _mark_submitted(job_id, screenshot=result["screenshot"] or "")
    return result


def _mark_submitted(job_id: str, *, screenshot: str) -> None:
    from store.status import mark_submitted

    try:
        mark_submitted(job_id, actor="auto_apply")
    except Exception as e:
        logger.warning("could not move %s to submitted: %s", job_id, e)

    try:
        from store.receipts import create_receipt

        create_receipt(
            job_id,
            "auto_apply",
            cover_letter_text=_cover_letter_for(job_id),
            resume_path=_cv_pdf_for(job_id),
            fields={"screenshot": screenshot},
        )
    except Exception as e:
        logger.warning("could not write receipt for %s: %s", job_id, e)

    store.audit("application_submitted", "job", job_id, {"via": "auto_apply"})
