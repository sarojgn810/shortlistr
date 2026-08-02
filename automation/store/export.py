"""Export SQLite state back to markdown for human editing."""

from __future__ import annotations

import os
from datetime import datetime

from config import PIPELINE_PATH
from paths import applications_file
from store import db as store
from store.enrich import is_placeholder


def export_pipeline() -> str:
    store.init_db()
    lines = ["# Shortlistr Job Pipeline", "", "## Pending", ""]
    with store.db() as conn:
        rows = conn.execute(
            """
            SELECT j.url, j.company, j.title, j.fit_score, j.source
            FROM pipeline p
            JOIN jobs j ON j.id = p.job_id
            WHERE p.status = 'pending'
            ORDER BY p.added_at DESC
            """
        ).fetchall()
    for r in rows:
        lines.append(
            f"- [ ] {r['url']} | {r['company']} | {r['title']} | score:{r['fit_score']} | {r['source']}"
        )
    lines.extend(["", "## Processed", ""])
    text = "\n".join(lines) + "\n"
    os.makedirs(os.path.dirname(PIPELINE_PATH), exist_ok=True)
    with open(PIPELINE_PATH, "w", encoding="utf-8") as f:
        f.write(text)
    return PIPELINE_PATH


def export_applications() -> str:
    """Write SQLite applications + evaluated pipeline jobs to applications.md."""
    store.init_db()
    path = applications_file()
    lines = [
        "# Applications Tracker",
        "",
        "| # | Date | Company | Role | Score | Status | PDF | Report | Notes |",
        "|---|------|---------|------|-------|--------|-----|--------|-------|",
    ]

    with store.db() as conn:
        app_rows = conn.execute(
            """
            SELECT a.*, j.url AS job_url,
                   ev.eval_score, ev.result_json
            FROM applications a
            LEFT JOIN jobs j ON j.id = a.job_id
            LEFT JOIN (
                SELECT job_id, score AS eval_score, result_json
                FROM eval_results e1
                WHERE id = (
                    SELECT id FROM eval_results e2
                    WHERE e2.job_id = e1.job_id ORDER BY id DESC LIMIT 1
                )
            ) ev ON ev.job_id = a.job_id
            ORDER BY a.id ASC
            """
        ).fetchall()

        if app_rows:
            for i, r in enumerate(app_rows, start=1):
                d = dict(r)
                company = d.get("company") or ""
                role = d.get("role") or ""
                if is_placeholder(company) and d.get("job_url"):
                    from store.enrich import company_title_from_url

                    c, _ = company_title_from_url(d["job_url"])
                    company = c or company
                score = d.get("score") or d.get("eval_score") or ""
                if score and "/" not in str(score):
                    score = f"{float(score):.1f}/5"
                elif not score:
                    score = "N/A"
                date = (d.get("applied_date") or d.get("created_at") or "")[:10]
                status = d.get("status") or "Evaluated"
                notes = (d.get("notes") or "").replace("|", "/")
                lines.append(
                    f"| {i} | {date} | {company} | {role} | {score} | {status} | | | {notes} |"
                )
        else:
            pipe_rows = conn.execute(
                """
                SELECT j.company, j.title, j.url, p.status, ev.eval_score, ev.result_json
                FROM pipeline p
                JOIN jobs j ON j.id = p.job_id
                LEFT JOIN (
                    SELECT job_id, score AS eval_score, result_json
                    FROM eval_results e1
                    WHERE id = (
                        SELECT id FROM eval_results e2
                        WHERE e2.job_id = e1.job_id ORDER BY id DESC LIMIT 1
                    )
                ) ev ON ev.job_id = j.id
                WHERE p.status IN ('evaluated', 'approved', 'submitted', 'skipped')
                ORDER BY p.added_at DESC
                """
            ).fetchall()
            today = datetime.now().strftime("%Y-%m-%d")
            for i, r in enumerate(pipe_rows, start=1):
                d = dict(r)
                score = d.get("eval_score")
                score_s = f"{float(score):.1f}/5" if score is not None else "N/A"
                lines.append(
                    f"| {i} | {today} | {d.get('company') or ''} | {d.get('title') or ''} | "
                    f"{score_s} | {d.get('status') or 'Evaluated'} | | | {d.get('url') or ''} |"
                )

    text = "\n".join(lines) + "\n"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def main() -> int:
    path = export_pipeline()
    print(f"Exported pipeline to {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
