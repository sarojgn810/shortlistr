#!/usr/bin/env python3
"""Validate shortlistr setup consistency (ported from cv-sync-check.mjs)."""

from __future__ import annotations

import os
import re
import sys
import time

from config import SHORTLISTR_ROOT
from paths import CV_PATH, PROFILE_PATH


def main() -> int:
    warnings: list[str] = []
    errors: list[str] = []

    if not os.path.exists(CV_PATH):
        errors.append("cv.md not found in project root. Create it with your CV in markdown format.")
    else:
        content = open(CV_PATH, encoding="utf-8").read()
        if len(content.strip()) < 100:
            warnings.append("cv.md seems too short. Make sure it contains your full CV.")

    if not os.path.exists(PROFILE_PATH):
        errors.append(
            "config/profile.yml not found. Copy from config/profile.example.yml and fill in your details."
        )
    else:
        profile = open(PROFILE_PATH, encoding="utf-8").read()
        for field in ("full_name", "email", "location"):
            if field not in profile or "Jane Smith" in profile:
                warnings.append(f"config/profile.yml may still have example data. Check field: {field}")
                break

    shared_path = os.path.join(SHORTLISTR_ROOT, "modes", "_shared.md")
    metric_pattern = re.compile(
        r"\b\d{2,4}\+?\s*(hours?|%|evals?|layers?|tests?|fields?|bases?)\b", re.I
    )
    if os.path.exists(shared_path):
        for i, line in enumerate(open(shared_path, encoding="utf-8"), 1):
            if any(x in line for x in ("NEVER hardcode", "NUNCA hardcode")):
                continue
            if line.startswith("#") or line.startswith("<!--"):
                continue
            m = metric_pattern.search(line)
            if m:
                warnings.append(
                    f"_shared.md:{i} — Possible hardcoded metric: \"{m.group(0)}\". "
                    "Should this be read from cv.md/article-digest.md?"
                )

    digest_path = os.path.join(SHORTLISTR_ROOT, "article-digest.md")
    if os.path.exists(digest_path):
        age_days = (time.time() - os.path.getmtime(digest_path)) / 86400
        if age_days > 30:
            warnings.append(
                f"article-digest.md is {round(age_days)} days old. "
                "Consider updating if your projects have new metrics."
            )

    print("\n=== shortlistr sync check ===\n")
    if not errors and not warnings:
        print("All checks passed.")
    else:
        if errors:
            print(f"ERRORS ({len(errors)}):")
            for e in errors:
                print(f"  ERROR: {e}")
        if warnings:
            print(f"\nWARNINGS ({len(warnings)}):")
            for w in warnings:
                print(f"  WARN: {w}")
    print("")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
