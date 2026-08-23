#!/usr/bin/env python3
"""Pipeline health check for applications.md (ported from verify-pipeline.mjs)."""

from __future__ import annotations

import os
import re
import sys

from paths import ADDITIONS_DIR, SHORTLISTR_ROOT, REPORTS_DIR, applications_file
from tracker_tools._common import CANONICAL_STATUSES_LOWER, STATUS_ALIASES, parse_app_line


def _error(msg: str, errors: list) -> None:
    print(f"❌ {msg}")
    errors.append(msg)


def _warn(msg: str, warnings: list) -> None:
    print(f"⚠️  {msg}")
    warnings.append(msg)


def _verify_sqlite(errors: list, warnings: list) -> None:
    """Check SQLite job store integrity when present."""
    db_path = os.path.join(SHORTLISTR_ROOT, "data", "shortlistr.db")
    if not os.path.exists(db_path):
        print("ℹ️  SQLite store not initialized (run make migrate-markdown or run_daily)")
        return
    try:
        sys.path.insert(0, os.path.join(SHORTLISTR_ROOT, "automation"))
        from store import db as store

        store.init_db()
        with store.db() as conn:
            jobs = conn.execute("SELECT COUNT(*) AS c FROM jobs").fetchone()["c"]
            pending = conn.execute(
                "SELECT COUNT(*) AS c FROM pipeline WHERE status='pending'"
            ).fetchone()["c"]
            orphan = conn.execute(
                """
                SELECT COUNT(*) AS c FROM pipeline p
                LEFT JOIN jobs j ON j.id = p.job_id WHERE j.id IS NULL
                """
            ).fetchone()["c"]
        print(f"✅ SQLite store: {jobs} jobs, {pending} pending pipeline")
        if orphan:
            _error(f"SQLite: {orphan} pipeline rows without matching jobs", errors)

        from store.status import PIPELINE_STATUSES
        bad_pipe = conn.execute(
            """
            SELECT COUNT(*) AS c FROM pipeline
            WHERE status NOT IN ({})
            """.format(",".join("?" * len(PIPELINE_STATUSES))),
            tuple(PIPELINE_STATUSES),
        ).fetchone()["c"]
        if bad_pipe:
            _error(f"SQLite: {bad_pipe} pipeline rows with invalid status", errors)

        receipts = conn.execute(
            "SELECT COUNT(*) AS c FROM application_receipts"
        ).fetchone()["c"]
        print(f"✅ SQLite receipts: {receipts}")
    except Exception as e:
        _warn(f"SQLite check skipped: {e}", warnings)


def main() -> int:
    apps_file = applications_file()
    errors: list[str] = []
    warnings: list[str] = []

    os.makedirs(os.path.join(SHORTLISTR_ROOT, "data"), exist_ok=True)
    os.makedirs(REPORTS_DIR, exist_ok=True)

    if not os.path.exists(apps_file):
        print("\n📊 No applications.md found. This is normal for a fresh setup.")
        print("   The file will be created when you evaluate your first offer.\n")
        return 0

    content = open(apps_file, encoding="utf-8").read()
    lines = content.split("\n")
    entries = []
    for line in lines:
        app = parse_app_line(line)
        if app:
            entries.append(app)

    print(f"\n📊 Checking {len(entries)} entries in applications.md\n")

    bad_statuses = 0
    for e in entries:
        clean = re.sub(r"\*\*", "", e["status"]).strip().lower()
        status_only = re.sub(r"\s+\d{4}-\d{2}-\d{2}.*$", "", clean).strip()
        if status_only not in CANONICAL_STATUSES_LOWER and status_only not in STATUS_ALIASES:
            _error(f'#{e["num"]}: Non-canonical status "{e["status"]}"', errors)
            bad_statuses += 1
        if "**" in e["status"]:
            _error(f'#{e["num"]}: Status contains markdown bold: "{e["status"]}"', errors)
            bad_statuses += 1
        if re.search(r"\d{4}-\d{2}-\d{2}", e["status"]):
            _error(
                f'#{e["num"]}: Status contains date: "{e["status"]}" — dates go in date column',
                errors,
            )
            bad_statuses += 1
    if bad_statuses == 0:
        print("✅ All statuses are canonical")

    company_role_map: dict[str, list] = {}
    dupes = 0
    for e in entries:
        key = (
            re.sub(r"[^a-z0-9]", "", e["company"].lower())
            + "::"
            + re.sub(r"[^a-z0-9 ]", "", e["role"].lower())
        )
        company_role_map.setdefault(key, []).append(e)
    for group in company_role_map.values():
        if len(group) > 1:
            nums = ", ".join(f"#{x['num']}" for x in group)
            _warn(
                f"Possible duplicates: {nums} ({group[0]['company']} — {group[0]['role']})",
                warnings,
            )
            dupes += 1
    if dupes == 0:
        print("✅ No exact duplicates found")

    broken_reports = 0
    for e in entries:
        m = re.search(r"\]\(([^)]+)\)", e["report"])
        if not m:
            continue
        report_path = os.path.join(SHORTLISTR_ROOT, m.group(1))
        if not os.path.exists(report_path):
            _error(f'#{e["num"]}: Report not found: {m.group(1)}', errors)
            broken_reports += 1
    if broken_reports == 0:
        print("✅ All report links valid")

    bad_scores = 0
    for e in entries:
        s = e["score"].replace("**", "").strip()
        if not re.match(r"^\d+\.?\d*/5$", s) and s not in ("N/A", "DUP"):
            _error(f'#{e["num"]}: Invalid score format: "{e["score"]}"', errors)
            bad_scores += 1
    if bad_scores == 0:
        print("✅ All scores valid")

    bad_rows = 0
    for line in lines:
        if not line.startswith("|"):
            continue
        if "---" in line or "Empresa" in line:
            continue
        if len(line.split("|")) < 9:
            _error(f"Row with <9 columns: {line[:80]}...", errors)
            bad_rows += 1
    if bad_rows == 0:
        print("✅ All rows properly formatted")

    pending_tsvs = 0
    if os.path.isdir(ADDITIONS_DIR):
        pending_tsvs = len([f for f in os.listdir(ADDITIONS_DIR) if f.endswith(".tsv")])
        if pending_tsvs > 0:
            _warn(f"{pending_tsvs} pending TSVs in tracker-additions/ (not merged)", warnings)
    if pending_tsvs == 0:
        print("✅ No pending TSVs")

    bold_scores = 0
    for e in entries:
        if "**" in e["score"]:
            _warn(f'#{e["num"]}: Score has markdown bold: "{e["score"]}"', warnings)
            bold_scores += 1
    if bold_scores == 0:
        print("✅ No bold in scores")

    _verify_sqlite(errors, warnings)

    print("\n" + "=" * 50)
    print(f"📊 Pipeline Health: {len(errors)} errors, {len(warnings)} warnings")
    if not errors and not warnings:
        print("🟢 Pipeline is clean!")
    elif not errors:
        print("🟡 Pipeline OK with warnings")
    else:
        print("🔴 Pipeline has errors — fix before proceeding")

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
