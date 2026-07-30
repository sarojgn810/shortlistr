"""Import markdown pipeline + applications into SQLite."""

from __future__ import annotations

import os
import re

from config import PIPELINE_PATH, DATA_DIR
from models.job import JobRecord, job_id_from_url
from paths import applications_file
from processors.pipeline_resolver import extract_pending_urls, resolve_pending_ats_jobs
from store import db as store


def migrate_pipeline() -> int:
    store.init_db()
    urls = extract_pending_urls()
    n = 0
    resolved_by_url = {r["url"]: r for r in resolve_pending_ats_jobs()}
    for url in urls:
        parts = url.split("|")
        url_only = parts[0].strip()
        company = parts[1].strip() if len(parts) > 1 else ""
        title = parts[2].strip() if len(parts) > 2 else ""

        resolved = resolved_by_url.get(url_only)
        if resolved:
            company = company or resolved.get("company", "")
            title = title or resolved.get("title", "")
            jd = resolved.get("jd_snippet") or resolved.get("description") or ""
            location = resolved.get("location", "")
        else:
            jd = ""
            location = ""

        from store.enrich import company_title_from_url, is_placeholder

        if is_placeholder(company):
            company, _ = company_title_from_url(url_only)
        if is_placeholder(company):
            company = "Unknown"
        if is_placeholder(title):
            title = "Unknown"

        job = JobRecord(
            url=url_only,
            source=resolved.get("source", "import") if resolved else "import",
            company=company,
            title=title,
            location=location,
            jd_text=jd,
        )
        store.upsert_job(job)
        store.add_to_pipeline(job.job_id)
        n += 1
    return n


def migrate_applications() -> int:
    path = applications_file()
    if not os.path.exists(path):
        return 0
    store.init_db()
    n = 0
    text = open(path, encoding="utf-8").read()
    for line in text.splitlines():
        if not line.startswith("|") or line.startswith("|---"):
            continue
        cols = [c.strip() for c in line.split("|")[1:-1]]
        if len(cols) < 6 or cols[0] == "#":
            continue
        try:
            num = cols[0]
            if not num.isdigit():
                continue
        except Exception:
            continue
        company, role = cols[2], cols[3]
        score = cols[4] if len(cols) > 4 else ""
        status = cols[5] if len(cols) > 5 else "Evaluated"
        with store.db() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO applications (company, role, score, status)
                VALUES (?, ?, ?, ?)
                """,
                (company, role, score, status),
            )
            n += 1
    return n


def main() -> int:
    p = migrate_pipeline()
    a = migrate_applications()
    print(f"Migrated {p} pipeline URLs and {a} application rows to {store.DB_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
