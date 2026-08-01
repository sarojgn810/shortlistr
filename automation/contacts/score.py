"""Confidence scoring + decision labels (Stage 6). Never auto-sends."""

from __future__ import annotations

from typing import Any

_VERIFY_W = {
    "valid": 1.0,
    "accept_all": 0.55,
    "unknown": 0.4,
    "unverified": 0.4,
    "invalid": 0.0,
    "error": 0.2,
}


def final_score(
    pattern_conf: float,
    verify_status: str,
    source_count: int,
    discovery_conf: float,
) -> float:
    v = _VERIFY_W.get((verify_status or "unknown").lower(), 0.4)
    src = min(max(int(source_count or 1), 0), 3) / 3.0
    return round(
        0.35 * float(pattern_conf or 0)
        + 0.35 * v
        + 0.15 * src
        + 0.15 * float(discovery_conf or 0),
        3,
    )


def decision_for(
    score: float,
    *,
    verify_status: str = "",
    is_catch_all: bool = False,
    mx_provider: str = "",
) -> str:
    """UI labels only — user still copies/sends."""
    vs = (verify_status or "").lower()
    if vs == "invalid":
        return "SKIP"
    if is_catch_all or mx_provider in ("proofpoint", "mimecast"):
        if score >= 0.8 and vs in ("valid", "accept_all", "unknown", "unverified"):
            return "REVIEW"  # prefer LinkedIn + portal; high pattern only
        return "SKIP" if score < 0.5 else "REVIEW"
    if score >= 0.80 and vs == "valid":
        return "SEND_NOW"
    if score >= 0.60:
        return "VERIFY_FIRST" if vs != "valid" else "SEND_NOW"
    if score >= 0.40:
        return "REVIEW"
    return "SKIP"


def map_verify_status(
    raw: str,
    *,
    mx_provider: str = "",
    is_catch_all: bool = False,
) -> str:
    s = (raw or "").lower().strip()
    # Hunter statuses
    if s in ("valid", "deliverable", "ok"):
        return "valid"
    if s in ("invalid", "undeliverable", "bad"):
        return "invalid"
    if s in ("accept_all", "accept-all", "catch_all", "catch-all", "webmail"):
        return "accept_all"
    if is_catch_all or mx_provider in ("proofpoint", "mimecast"):
        if s in ("unknown", "unverified", "", "risky"):
            return "accept_all"
    if s in ("unverified",):
        return "unverified"
    return s or "unknown"


def rank_people(people: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """ATS field > JD > SERP-named > title-inferred; then discovery_conf."""
    source_rank = {
        "ats_field": 0,
        "jd_email": 1,
        "jd_regex": 2,
        "github": 3,
        "serp": 4,
        "title_ladder": 5,
        "user": 6,
    }

    def key(p: dict[str, Any]) -> tuple:
        src = str(p.get("source") or "")
        return (
            source_rank.get(src, 9),
            int(p.get("seniority_rank") or 99),
            -float(p.get("discovery_conf") or 0),
        )

    return sorted(people, key=key)
