#!/usr/bin/env python3
"""Merge batch tracker additions into applications.md."""

from __future__ import annotations

import os
import re
import shutil
import sys

from paths import ADDITIONS_DIR, MERGED_DIR, applications_file
from tracker_tools._common import (
    extract_report_num,
    normalize_company,
    parse_app_line,
    parse_score,
    role_fuzzy_match,
    validate_status,
)
from tracker_tools import verify_pipeline


def _col_looks_like_score(val: str) -> bool:
    return bool(re.match(r"^\d+\.?\d*/5$", val)) or val in ("N/A", "DUP")


def _col_looks_like_status(val: str) -> bool:
    return bool(re.match(
        r"^(evaluated|applied|responded|interview|offer|rejected|discarded|skip|"
        r"evaluada|aplicado|respondido|entrevista|oferta|rechazado|descartado|"
        r"no aplicar|cerrada|duplicado|repost|condicional|hold|monitor)",
        val, re.I,
    ))


def parse_tsv_content(content: str, filename: str) -> dict | None:
    content = content.strip()
    if not content:
        return None

    if content.startswith("|"):
        parts = [p.strip() for p in content.split("|") if p.strip()]
        if len(parts) < 8:
            print(f"⚠️  Skipping malformed pipe-delimited {filename}: {len(parts)} fields")
            return None
        addition = {
            "num": int(parts[0]),
            "date": parts[1],
            "company": parts[2],
            "role": parts[3],
            "score": parts[4],
            "status": validate_status(parts[5]),
            "pdf": parts[6],
            "report": parts[7],
            "notes": parts[8] if len(parts) > 8 else "",
        }
    else:
        parts = content.split("\t")
        if len(parts) < 8:
            print(f"⚠️  Skipping malformed TSV {filename}: {len(parts)} fields")
            return None
        col4, col5 = parts[4].strip(), parts[5].strip()
        if _col_looks_like_status(col4) and not _col_looks_like_score(col4):
            status_col, score_col = col4, col5
        elif _col_looks_like_score(col4) and _col_looks_like_status(col5):
            status_col, score_col = col5, col4
        elif _col_looks_like_score(col5) and not _col_looks_like_score(col4):
            status_col, score_col = col4, col5
        else:
            status_col, score_col = col4, col5
        addition = {
            "num": int(parts[0]),
            "date": parts[1],
            "company": parts[2],
            "role": parts[3],
            "status": validate_status(status_col),
            "score": score_col,
            "pdf": parts[6],
            "report": parts[7],
            "notes": parts[8] if len(parts) > 8 else "",
        }

    if addition["num"] == 0:
        print(f"⚠️  Skipping {filename}: invalid entry number")
        return None
    return addition


def main(argv: list[str] | None = None) -> int:
    args = argv or sys.argv
    dry_run = "--dry-run" in args
    verify = "--verify" in args
    apps_file = applications_file()

    if not os.path.exists(apps_file):
        print("No applications.md found. Nothing to merge into.")
        return 0

    app_lines = open(apps_file, encoding="utf-8").read().split("\n")
    existing_apps = []
    max_num = 0
    for line in app_lines:
        if line.startswith("|") and "---" not in line and "Empresa" not in line:
            app = parse_app_line(line)
            if app:
                existing_apps.append(app)
                max_num = max(max_num, app["num"])

    print(f"📊 Existing: {len(existing_apps)} entries, max #{max_num}")

    if not os.path.isdir(ADDITIONS_DIR):
        print("No tracker-additions directory found.")
        return 0

    tsv_files = sorted(
        [f for f in os.listdir(ADDITIONS_DIR) if f.endswith(".tsv")],
        key=lambda f: int(re.sub(r"\D", "", f) or 0),
    )
    if not tsv_files:
        print("✅ No pending additions to merge.")
        return 0

    print(f"📥 Found {len(tsv_files)} pending additions")
    added = updated = skipped = 0
    new_lines = []

    for file in tsv_files:
        path = os.path.join(ADDITIONS_DIR, file)
        content = open(path, encoding="utf-8").read().strip()
        addition = parse_tsv_content(content, file)
        if not addition:
            skipped += 1
            continue

        report_num = extract_report_num(addition["report"])
        duplicate = None
        if report_num:
            duplicate = next(
                (a for a in existing_apps if extract_report_num(a["report"]) == report_num),
                None,
            )
        if not duplicate:
            duplicate = next((a for a in existing_apps if a["num"] == addition["num"]), None)
        if not duplicate:
            nc = normalize_company(addition["company"])
            duplicate = next(
                (
                    a for a in existing_apps
                    if normalize_company(a["company"]) == nc
                    and role_fuzzy_match(addition["role"], a["role"])
                ),
                None,
            )

        if duplicate:
            new_score = parse_score(addition["score"])
            old_score = parse_score(duplicate["score"])
            if new_score > old_score:
                print(
                    f'🔄 Update: #{duplicate["num"]} {addition["company"]} — '
                    f'{addition["role"]} ({old_score}→{new_score})'
                )
                try:
                    line_idx = app_lines.index(duplicate["raw"])
                except ValueError:
                    line_idx = -1
                if line_idx >= 0:
                    app_lines[line_idx] = (
                        f'| {duplicate["num"]} | {addition["date"]} | {addition["company"]} | '
                        f'{addition["role"]} | {addition["score"]} | {duplicate["status"]} | '
                        f'{duplicate["pdf"]} | {addition["report"]} | '
                        f'Re-eval {addition["date"]} ({old_score}→{new_score}). {addition["notes"]} |'
                    )
                    updated += 1
            else:
                print(
                    f'⏭️  Skip: {addition["company"]} — {addition["role"]} '
                    f'(existing #{duplicate["num"]} {old_score} >= new {new_score})'
                )
                skipped += 1
        else:
            entry_num = addition["num"] if addition["num"] > max_num else max_num + 1
            if addition["num"] > max_num:
                max_num = addition["num"]
            else:
                max_num = entry_num
            new_line = (
                f'| {entry_num} | {addition["date"]} | {addition["company"]} | '
                f'{addition["role"]} | {addition["score"]} | {addition["status"]} | '
                f'{addition["pdf"]} | {addition["report"]} | {addition["notes"]} |'
            )
            new_lines.append(new_line)
            added += 1
            print(f'➕ Add #{entry_num}: {addition["company"]} — {addition["role"]} ({addition["score"]})')

    if new_lines:
        insert_idx = -1
        for i, line in enumerate(app_lines):
            if line.startswith("|") and "---" in line:
                insert_idx = i + 1
                break
        if insert_idx >= 0:
            app_lines[insert_idx:insert_idx] = new_lines

    if not dry_run:
        with open(apps_file, "w", encoding="utf-8") as f:
            f.write("\n".join(app_lines))
        os.makedirs(MERGED_DIR, exist_ok=True)
        for file in tsv_files:
            shutil.move(
                os.path.join(ADDITIONS_DIR, file),
                os.path.join(MERGED_DIR, file),
            )
        print(f"\n✅ Moved {len(tsv_files)} TSVs to merged/")

    print(f"\n📊 Summary: +{added} added, 🔄{updated} updated, ⏭️{skipped} skipped")
    if dry_run:
        print("(dry-run — no changes written)")

    if verify and not dry_run:
        print("\n--- Running verification ---")
        return verify_pipeline.main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
