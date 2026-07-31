"""Résumé prep status — baseline cv.md vs what we actually send (J1.4).

generate_cv renders the same cv.md through the user's Resume-page template.
There is no per-job text rewrite, so inventing an "Applying for…" header (or
diffing against LaTeX source) produced odd "2 changes" / 100+ TeX noise in the UI.
This module reports readiness honestly: same content, PDF ready or not.
"""

from __future__ import annotations

import json
import os
from typing import Any

from store import db as store
from store.status import validate_job_id


def _cv_path() -> str:
    import config

    return config.CV_MD_PATH


def _read_baseline() -> str:
    path = _cv_path()
    if not os.path.exists(path):
        return ""
    return open(path, encoding="utf-8").read().strip()


def build_tailored_text(job: dict) -> str:
    """Text we treat as the per-job résumé — same as baseline (no fake overlay)."""
    baseline = _read_baseline()
    if baseline:
        return baseline
    company = job.get("company") or "Company"
    title = job.get("title") or "Role"
    return f"{title} at {company}".strip()


def _job_dict_from_row(row: dict) -> dict:
    return {
        "company": row.get("company") or "",
        "title": row.get("title") or "",
        "url": row.get("url") or "",
        "job_id": row.get("id") or "",
    }


def _meta(row: dict) -> dict:
    try:
        return json.loads(row.get("metadata_json") or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}


def _artifact_paths(meta: dict) -> dict[str, str | None]:
    html = meta.get("tailored_html_path") or meta.get("tailored_resume_html")
    tex = meta.get("tailored_tex_path")
    pdf = meta.get("tailored_pdf_path")
    # Legacy bug: LaTeX path was stored under tailored_html_path.
    if html and str(html).lower().endswith(".tex"):
        tex = tex or html
        html = None
    if tex and not str(tex).lower().endswith(".tex"):
        tex = None
    if html and not str(html).lower().endswith((".html", ".htm")):
        # Unknown source — don't treat as HTML body for diffs.
        html = None
    return {"html": html, "tex": tex, "pdf": pdf}


def compute_diff(job_id: str) -> dict[str, Any]:
    jid = validate_job_id(job_id)
    store.init_db()

    with store.db() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (jid,)).fetchone()
    if not row:
        raise ValueError(f"Job not found: {jid}")

    job = _job_dict_from_row(dict(row))
    company = job["company"] or "Company"
    role = job["title"] or "Role"
    baseline = _read_baseline()
    arts = _artifact_paths(_meta(dict(row)))

    highlights: list[str] = []
    pdf_ready = bool(arts["pdf"] and os.path.isfile(arts["pdf"]))
    html_ready = bool(arts["html"] and os.path.isfile(arts["html"]))
    tex_ready = bool(arts["tex"] and os.path.isfile(arts["tex"]))

    if not baseline:
        summary = "No résumé on file yet — upload a résumé (cv.md) first."
        highlights = ["Open Profile / Resume and upload your CV."]
    elif pdf_ready:
        summary = (
            f"PDF ready for {role} at {company} — same content as your baseline résumé."
        )
        highlights = [
            "Rendered from cv.md with the template you picked on Resume.",
            f"File: {os.path.basename(arts['pdf'] or '')}",
        ]
        if tex_ready:
            highlights.append("Built with LaTeX (ATS-friendly).")
        elif html_ready:
            highlights.append("Built with the HTML renderer.")
    else:
        summary = (
            f"Will use your baseline résumé for {role} at {company} "
            "(no per-job text edits)."
        )
        highlights = [
            "Content matches cv.md — generate Prep to produce the PDF.",
        ]

    preview = baseline[:500] if baseline else ""

    return {
        "job_id": jid,
        "company": company,
        "role": role,
        "change_count": 0,
        "additions": 0,
        "removals": 0,
        "same_as_baseline": True,
        "pdf_ready": pdf_ready,
        "summary": summary,
        "highlights": highlights,
        # Keep `diff` as human lines for older UI that joins the list.
        "diff": highlights,
        "baseline_path": _cv_path() if os.path.exists(_cv_path()) else None,
        "tailored_preview": preview,
        "pdf_path": arts["pdf"] if pdf_ready else None,
    }


def format_diff_text(data: dict[str, Any]) -> str:
    lines = [
        data.get("summary") or f"{data.get('change_count', 0)} change(s)",
        f"{data.get('company', '?')} — {data.get('role', '?')}",
        "=" * 50,
    ]
    for h in data.get("highlights") or data.get("diff") or []:
        lines.append(f"• {h}")
    if not data.get("highlights") and not data.get("diff"):
        lines.append("No textual differences (baseline matches tailored).")
        preview = data.get("tailored_preview") or ""
        if preview:
            lines.append("")
            lines.append("Preview:")
            lines.append(preview[:300])
    return "\n".join(lines) + "\n"


def record_tailored_artifact(job_id: str, source_path: str, pdf_path: str | None = None) -> None:
    """Store pointers to generated CV artifacts in job metadata."""
    jid = validate_job_id(job_id)
    store.init_db()
    with store.db() as conn:
        row = conn.execute(
            "SELECT metadata_json FROM jobs WHERE id = ?", (jid,)
        ).fetchone()
        if not row:
            raise ValueError(f"Job not found: {jid}")
        try:
            meta = json.loads(row["metadata_json"] or "{}")
        except json.JSONDecodeError:
            meta = {}

        src = source_path or ""
        lower = src.lower()
        if lower.endswith(".tex"):
            meta["tailored_tex_path"] = src
            # Clear the legacy mis-filed HTML key if it pointed at this .tex
            if str(meta.get("tailored_html_path") or "").lower().endswith(".tex"):
                meta.pop("tailored_html_path", None)
        elif lower.endswith((".html", ".htm")):
            meta["tailored_html_path"] = src
        elif src:
            meta["tailored_source_path"] = src

        if pdf_path:
            meta["tailored_pdf_path"] = pdf_path
        conn.execute(
            "UPDATE jobs SET metadata_json = ?, updated_at = datetime('now') WHERE id = ?",
            (json.dumps(meta), jid),
        )
