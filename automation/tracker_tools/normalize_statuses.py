#!/usr/bin/env python3
"""Clean non-canonical statuses in applications.md."""

from __future__ import annotations

import os
import re
import shutil
import sys

from paths import applications_file


def normalize_status(raw: str) -> dict:
    s = raw.replace("**", "").strip()
    lower = s.lower()

    if re.match(r"^duplicado", s, re.I) or re.match(r"^dup\b", s, re.I):
        return {"status": "Discarded", "move_to_notes": raw.strip()}
    if re.match(r"^cerrada$", s, re.I):
        return {"status": "Discarded"}
    if re.match(r"^cancelada", s, re.I):
        return {"status": "Discarded"}
    if re.match(r"^descartad[ao]$", s, re.I):
        return {"status": "Discarded"}
    if re.match(r"^rechazad[ao]$", s, re.I):
        return {"status": "Rejected"}
    if re.match(r"^rechazado\s+\d{4}", s, re.I):
        return {"status": "Rejected"}
    if re.match(r"^aplicado\s+\d{4}", s, re.I):
        return {"status": "Applied"}
    if re.match(r"^(condicional|hold|evaluar|verificar)$", s, re.I):
        return {"status": "Evaluated"}
    if re.match(r"^monitor$", s, re.I):
        return {"status": "SKIP"}
    if re.search(r"geo.?blocker", s, re.I):
        return {"status": "SKIP"}
    if re.match(r"^repost", s, re.I):
        return {"status": "Discarded", "move_to_notes": raw.strip()}
    if s in ("—", "-", ""):
        return {"status": "Discarded"}

    canonical = [
        "Evaluated", "Applied", "Responded", "Interview",
        "Offer", "Rejected", "Discarded", "SKIP",
    ]
    for c in canonical:
        if lower == c.lower():
            return {"status": c}

    spanish = {
        "evaluada": "Evaluated",
        "aplicado": "Applied", "enviada": "Applied", "aplicada": "Applied",
        "applied": "Applied", "sent": "Applied",
        "respondido": "Responded", "entrevista": "Interview", "oferta": "Offer",
        "cerrada": "Discarded", "descartada": "Discarded",
        "no aplicar": "SKIP", "no_aplicar": "SKIP", "skip": "SKIP",
    }
    if lower in spanish:
        return {"status": spanish[lower]}

    return {"status": None, "unknown": True}


def main(argv: list[str] | None = None) -> int:
    dry_run = "--dry-run" in (argv or sys.argv)
    apps_file = applications_file()

    if not os.path.exists(apps_file):
        print("No applications.md found. Nothing to normalize.")
        return 0

    lines = open(apps_file, encoding="utf-8").read().split("\n")
    changes = 0
    unknowns = []

    for i, line in enumerate(lines):
        if not line.startswith("|"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 9:
            continue
        if parts[1] in ("#", "---", ""):
            continue
        try:
            num = int(parts[1])
        except ValueError:
            continue

        raw_status = parts[6]
        result = normalize_status(raw_status)
        if result.get("unknown"):
            unknowns.append({"num": num, "raw": raw_status, "line": i + 1})
            continue
        if result["status"] == raw_status:
            continue

        old_status = raw_status
        parts[6] = result["status"]
        if result.get("move_to_notes"):
            existing = parts[9] if len(parts) > 9 else ""
            note = result["move_to_notes"]
            if note not in (existing or ""):
                parts[9] = note + ((". " + existing) if existing else "")
        if parts[5]:
            parts[5] = parts[5].replace("**", "")
        lines[i] = "| " + " | ".join(parts[1:-1]) + " |"
        changes += 1
        print(f'#{num}: "{old_status}" → "{result["status"]}"')

    if unknowns:
        print(f"\n⚠️  {len(unknowns)} unknown statuses:")
        for u in unknowns:
            print(f'  #{u["num"]} (line {u["line"]}): "{u["raw"]}"')

    print(f"\n📊 {changes} statuses normalized")

    if not dry_run and changes > 0:
        shutil.copy2(apps_file, apps_file + ".bak")
        with open(apps_file, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        print("✅ Written to applications.md (backup: applications.md.bak)")
    elif dry_run:
        print("(dry-run — no changes written)")
    else:
        print("✅ No changes needed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
