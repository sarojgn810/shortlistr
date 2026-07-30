#!/usr/bin/env python3
"""Remove duplicate entries from applications.md."""

from __future__ import annotations

import os
import re
import shutil
import sys

from paths import applications_file
from tracker_tools._common import parse_app_line, parse_score

STATUS_RANK = {
    "skip": 0, "discarded": 0, "rejected": 1, "evaluated": 2,
    "applied": 3, "responded": 4, "interview": 5, "offer": 6,
    "no_aplicar": 0, "no aplicar": 0, "descartado": 0, "descartada": 0,
    "rechazado": 1, "rechazada": 1, "evaluada": 2, "aplicado": 3,
    "respondido": 4, "entrevista": 5, "oferta": 6,
}

ROLE_STOPWORDS = {
    "senior", "junior", "lead", "staff", "principal", "head", "chief",
    "manager", "director", "associate", "intern", "contractor",
    "remote", "hybrid", "onsite", "engineer", "engineering",
}

LOCATION_STOPWORDS = {
    "tokyo", "japan", "london", "berlin", "paris", "singapore",
    "york", "francisco", "angeles", "seattle", "austin", "boston",
    "chicago", "denver", "toronto", "amsterdam", "dublin", "sydney",
    "remote", "global", "emea", "apac", "latam",
}


def normalize_company(name: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", name.lower().replace("(", "").replace(")", "")).strip()


def normalize_role(role: str) -> str:
    return re.sub(r"[^a-z0-9 /]", "", role.lower().replace("(", " ").replace(")", " ")).strip()


def role_match(a: str, b: str) -> bool:
    def filt(words: list[str]) -> list[str]:
        return [w for w in words if w not in ROLE_STOPWORDS and w not in LOCATION_STOPWORDS]

    words_a = filt([w for w in normalize_role(a).split() if len(w) > 2])
    words_b = filt([w for w in normalize_role(b).split() if len(w) > 2])
    if not words_a or not words_b:
        return False
    overlap = [w for w in words_a if w in words_b]
    smaller = min(len(words_a), len(words_b))
    return len(overlap) >= 2 and (len(overlap) / smaller) >= 0.6


def main(argv: list[str] | None = None) -> int:
    dry_run = "--dry-run" in (argv or sys.argv)
    apps_file = applications_file()

    if not os.path.exists(apps_file):
        print("No applications.md found. Nothing to dedup.")
        return 0

    lines = open(apps_file, encoding="utf-8").read().split("\n")
    entries = []
    entry_line_map: dict[int, int] = {}

    for i, line in enumerate(lines):
        if not line.startswith("|"):
            continue
        app = parse_app_line(line)
        if app and app["num"] > 0:
            entries.append(app)
            entry_line_map[app["num"]] = i

    print(f"📊 {len(entries)} entries loaded")

    groups: dict[str, list] = {}
    for entry in entries:
        key = normalize_company(entry["company"])
        groups.setdefault(key, []).append(entry)

    removed = 0
    lines_to_remove: set[int] = set()

    for company_entries in groups.values():
        if len(company_entries) < 2:
            continue
        processed: set[int] = set()
        for i, e1 in enumerate(company_entries):
            if i in processed:
                continue
            cluster = [e1]
            processed.add(i)
            for j in range(i + 1, len(company_entries)):
                if j in processed:
                    continue
                if role_match(e1["role"], company_entries[j]["role"]):
                    cluster.append(company_entries[j])
                    processed.add(j)
            if len(cluster) < 2:
                continue

            cluster.sort(key=lambda x: parse_score(x["score"]), reverse=True)
            keeper = cluster[0]
            best_rank = STATUS_RANK.get(keeper["status"].lower(), 0)
            best_status = keeper["status"]
            for dup in cluster[1:]:
                rank = STATUS_RANK.get(dup["status"].lower(), 0)
                if rank > best_rank:
                    best_rank = rank
                    best_status = dup["status"]

            if best_status != keeper["status"]:
                line_idx = entry_line_map.get(keeper["num"])
                if line_idx is not None:
                    parts = [p.strip() for p in lines[line_idx].split("|")]
                    parts[6] = best_status
                    lines[line_idx] = "| " + " | ".join(parts[1:-1]) + " |"
                    print(f'  📝 #{keeper["num"]}: status promoted to "{best_status}"')

            for dup in cluster[1:]:
                line_idx = entry_line_map.get(dup["num"])
                if line_idx is not None:
                    lines_to_remove.add(line_idx)
                    removed += 1
                    print(
                        f'🗑️  Remove #{dup["num"]} ({dup["company"]} — {dup["role"]}, '
                        f'{dup["score"]}) → kept #{keeper["num"]} ({keeper["score"]})'
                    )

    for idx in sorted(lines_to_remove, reverse=True):
        del lines[idx]

    print(f"\n📊 {removed} duplicates removed")

    if not dry_run and removed > 0:
        shutil.copy2(apps_file, apps_file + ".bak")
        with open(apps_file, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        print("✅ Written to applications.md (backup: applications.md.bak)")
    elif dry_run:
        print("(dry-run — no changes written)")
    else:
        print("✅ No duplicates found")
    return 0


if __name__ == "__main__":
    sys.exit(main())
