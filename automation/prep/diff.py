"""Résumé diff — baseline cv.md vs per-job tailored overlay (J1.4)."""

from __future__ import annotations

import difflib
import json
import os
import re
from html import unescape
from typing import Any

from config import CV_MD_PATH, OUTPUT_DIR
from store import db as store
from store.status import validate_job_id

_TAG_RE = re.compile(r"<[^>]+>")


def _read_baseline() -> str:
    if not os.path.exists(CV_MD_PATH):
        return ""
    return open(CV_MD_PATH, encoding="utf-8").read().strip()


def _strip_html(html: str) -> str:
    text = _TAG_RE.sub(" ", html)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def build_tailored_text(job: dict) -> str:
    """Plain-text tailored CV: baseline + role-specific header."""
    baseline = _read_baseline()
    company = job.get("company") or "Company"
    title = job.get("title") or "Role"
    header = f"# Applying for: {title} at {company}\n"
    if not baseline:
        return header.strip()
    return f"{header}\n{baseline}".strip()


def _job_dict_from_row(row: dict) -> dict:
    return {
        "company": row.get("company") or "",
        "title": row.get("title") or "",
        "url": row.get("url") or "",
        "job_id": row.get("id") or "",
    }


def compute_diff(job_id: str) -> dict[str, Any]:
    jid = validate_job_id(job_id)
    store.init_db()

    with store.db() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (jid,)).fetchone()
    if not row:
        raise ValueError(f"Job not found: {jid}")

    job = _job_dict_from_row(dict(row))
    baseline = _read_baseline()
    tailored = build_tailored_text(job)

    # Also diff against saved HTML artifact if present
    meta = {}
    try:
        meta = json.loads(row["metadata_json"] or "{}")
    except (TypeError, json.JSONDecodeError):
        pass
    html_path = meta.get("tailored_html_path") or meta.get("tailored_resume_html")
    if html_path and os.path.isfile(html_path):
        tailored = _strip_html(open(html_path, encoding="utf-8").read())

    baseline_lines = baseline.splitlines() or [""]
    tailored_lines = tailored.splitlines() or [""]

    diff = list(
        difflib.unified_diff(
            baseline_lines,
            tailored_lines,
            fromfile="cv.md (baseline)",
            tofile=f"tailored ({job['company']})",
            lineterm="",
        )
    )

    changes = [ln for ln in diff if ln.startswith("+") and not ln.startswith("+++")]
    removals = [ln for ln in diff if ln.startswith("-") and not ln.startswith("---")]

    return {
        "job_id": jid,
        "company": job["company"],
        "role": job["title"],
        "change_count": len(changes) + len(removals),
        "additions": len(changes),
        "removals": len(removals),
        "diff": diff,
        "baseline_path": CV_MD_PATH if os.path.exists(CV_MD_PATH) else None,
        "tailored_preview": tailored[:500],
    }


def format_diff_text(data: dict[str, Any]) -> str:
    n = data.get("change_count", 0)
    header = (
        f"{data.get('change_count', 0)} change(s) · nothing sent yet\n"
        f"{data.get('company', '?')} — {data.get('role', '?')}\n"
        f"{'=' * 50}\n"
    )
    body = "\n".join(data.get("diff") or [])
    if not body:
        header += "No textual differences (baseline matches tailored).\n"
        preview = data.get("tailored_preview") or ""
        if preview:
            header += f"\nTailored preview:\n{preview[:300]}...\n"
    else:
        header += body + "\n"
    return header


def record_tailored_artifact(job_id: str, html_path: str, pdf_path: str | None = None) -> None:
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
        meta["tailored_html_path"] = html_path
        if pdf_path:
            meta["tailored_pdf_path"] = pdf_path
        conn.execute(
            "UPDATE jobs SET metadata_json = ?, updated_at = datetime('now') WHERE id = ?",
            (json.dumps(meta), jid),
        )
