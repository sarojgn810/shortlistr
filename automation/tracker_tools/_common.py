"""Shared parsing helpers for applications.md and tracker TSVs."""

from __future__ import annotations

import re
from typing import Any

CANONICAL_STATES = [
    "Evaluated", "Applied", "Responded", "Interview",
    "Offer", "Rejected", "Discarded", "SKIP",
]

CANONICAL_STATUSES_LOWER = [
    "evaluated", "applied", "responded", "interview",
    "offer", "rejected", "discarded", "skip",
]

STATUS_ALIASES = {
    "evaluada": "evaluated", "condicional": "evaluated", "hold": "evaluated",
    "evaluar": "evaluated", "verificar": "evaluated",
    "aplicado": "applied", "enviada": "applied", "aplicada": "applied",
    "sent": "applied",
    "respondido": "responded",
    "entrevista": "interview",
    "oferta": "offer",
    "rechazado": "rejected", "rechazada": "rejected",
    "descartado": "discarded", "descartada": "discarded",
    "cerrada": "discarded", "cancelada": "discarded",
    "no aplicar": "skip", "no_aplicar": "skip", "monitor": "skip",
    "geo blocker": "skip",
}

STATUS_ALIASES_TITLE = {
    "evaluada": "Evaluated", "condicional": "Evaluated", "hold": "Evaluated",
    "evaluar": "Evaluated", "verificar": "Evaluated",
    "aplicado": "Applied", "enviada": "Applied", "aplicada": "Applied",
    "applied": "Applied", "sent": "Applied",
    "respondido": "Responded",
    "entrevista": "Interview",
    "oferta": "Offer",
    "rechazado": "Rejected", "rechazada": "Rejected",
    "descartado": "Discarded", "descartada": "Discarded",
    "cerrada": "Discarded", "cancelada": "Discarded",
    "no aplicar": "SKIP", "no_aplicar": "SKIP", "skip": "SKIP",
    "monitor": "SKIP", "geo blocker": "SKIP",
}


def validate_status(status: str) -> str:
    clean = re.sub(r"\*\*", "", status)
    clean = re.sub(r"\s+\d{4}-\d{2}-\d{2}.*$", "", clean).strip()
    lower = clean.lower()
    for valid in CANONICAL_STATES:
        if valid.lower() == lower:
            return valid
    if lower in STATUS_ALIASES_TITLE:
        return STATUS_ALIASES_TITLE[lower]
    if re.match(r"^(duplicado|dup|repost)", lower):
        return "Discarded"
    print(f'⚠️  Non-canonical status "{status}" → defaulting to "Evaluated"')
    return "Evaluated"


def normalize_company(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def parse_score(s: str) -> float:
    m = re.search(r"([\d.]+)", s.replace("**", ""))
    return float(m.group(1)) if m else 0.0


def parse_app_line(line: str) -> dict[str, Any] | None:
    if not line.startswith("|"):
        return None
    parts = [p.strip() for p in line.split("|")]
    if len(parts) < 9:
        return None
    try:
        num = int(parts[1])
    except ValueError:
        return None
    if num == 0:
        return None
    return {
        "num": num,
        "date": parts[2],
        "company": parts[3],
        "role": parts[4],
        "score": parts[5],
        "status": parts[6],
        "pdf": parts[7],
        "report": parts[8],
        "notes": parts[9] if len(parts) > 9 else "",
        "raw": line,
    }


def role_fuzzy_match(a: str, b: str) -> bool:
    words_a = [w for w in a.lower().split() if len(w) > 3]
    words_b = [w for w in b.lower().split() if len(w) > 3]
    overlap = [w for w in words_a if any(wb in w or w in wb for wb in words_b)]
    return len(overlap) >= 2


def extract_report_num(report_str: str) -> int | None:
    m = re.search(r"\[(\d+)\]", report_str)
    return int(m.group(1)) if m else None
