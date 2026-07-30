"""Multi-dimension LinkedIn profile scoring — heuristic only."""

from __future__ import annotations

import re
from typing import Any

from linkedin_optimizer.roles import get_role

_METRIC_RE = re.compile(
    r"(\d+\s*%|\d+\s*x\b|\$\d|\d+\s*(ms|s|min|hours?|days?|weeks?|months?|years?|"
    r"k\b|m\b|million|billion|users?|requests?|nodes?|clusters?|teams?))",
    re.I,
)
_GENERIC = {
    "passionate", "synergy", "rockstar", "ninja", "guru", "driven professional",
    "hard worker", "team player", "results-oriented", "self-starter",
}
try:
    from writing.policy import LOCAL_FLUFF

    _GENERIC = set(_GENERIC) | set(LOCAL_FLUFF)
except Exception:
    pass


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def _find_keywords(haystack: str, keywords: list[str]) -> tuple[list[str], list[str]]:
    found, missing = [], []
    h = _norm(haystack)
    for kw in keywords:
        if kw.lower() in h:
            found.append(kw)
        else:
            missing.append(kw)
    return found, missing


def _quantification_ratio(bullets: list[str]) -> float:
    if not bullets:
        return 0.0
    hit = sum(1 for b in bullets if _METRIC_RE.search(b))
    return hit / max(1, len(bullets))


def score_profile(profile: dict[str, Any], role_id: str) -> dict[str, Any]:
    role = get_role(role_id)
    raw = _norm(profile.get("raw") or "")
    headline = profile.get("headline") or ""
    about = profile.get("about") or ""
    skills = profile.get("skills") or []
    experience = profile.get("experience") or []
    bullets: list[str] = []
    for job in experience:
        bullets.extend(job.get("bullets") or [])

    corpus = " ".join(
        [
            headline,
            about,
            " ".join(skills),
            " ".join(bullets),
            " ".join(f"{j.get('title','')} {j.get('company','')}" for j in experience),
        ]
    )

    must_found, must_missing = _find_keywords(corpus, role["must_keywords"])
    nice_found, nice_missing = _find_keywords(corpus, role["nice_keywords"])
    title_found, title_missing = _find_keywords(
        f"{headline} {about}", role["search_titles"]
    )

    keyword_score = int(
        round(
            100
            * (
                0.7 * (len(must_found) / max(1, len(role["must_keywords"])))
                + 0.3 * (len(nice_found) / max(1, len(role["nice_keywords"])))
            )
        )
    )

    # Role alignment: title variants in headline/about + seniority terms
    seniority_hit = any(s in _norm(headline + " " + about) for s in role["seniority"])
    role_alignment = int(
        round(
            100
            * (
                0.55 * (1.0 if title_found else 0.0)
                + 0.25 * min(1.0, len(must_found) / 6)
                + 0.20 * (1.0 if seniority_hit else 0.35)
            )
        )
    )

    quant_ratio = _quantification_ratio(bullets) if bullets else (
        1.0 if _METRIC_RE.search(about) else 0.0
    )
    quantification = int(round(100 * quant_ratio))

    # Clarity: length bounds, low generic fluff
    about_len = len(about.split())
    clarity = 70
    if 80 <= about_len <= 260:
        clarity += 20
    elif about_len < 40:
        clarity -= 25
    elif about_len > 400:
        clarity -= 15
    fluff = sum(1 for g in _GENERIC if g in _norm(about + " " + headline))
    clarity -= min(30, fluff * 10)
    if len(headline) < 20:
        clarity -= 15
    if len(headline) > 220:
        clarity -= 10
    clarity = max(0, min(100, clarity))

    verb_hits = sum(
        1 for b in bullets for v in role["impact_verbs"] if b.lower().startswith(v) or f" {v} " in f" {b.lower()} "
    )
    impact = int(round(100 * min(1.0, (verb_hits / max(3, len(bullets) or 3)) + 0.2 * quant_ratio)))

    completeness = 0
    checks = {
        "headline": bool(headline.strip()),
        "about": bool(about.strip()) and about_len >= 40,
        "experience": bool(experience) and any((j.get("bullets") or []) for j in experience),
        "skills": len(skills) >= 5,
        "location": bool((profile.get("location") or "").strip()),
        "open_to_work": bool((profile.get("open_to_work") or "").strip()),
        "featured": bool((profile.get("featured") or "").strip()),
        "contact": bool((profile.get("contact") or "").strip()),
    }
    completeness = int(round(100 * sum(1 for v in checks.values() if v) / len(checks)))

    # Consistency: headline keywords also appear in about/experience
    hl_tokens = [t for t in re.findall(r"[a-zA-Z][a-zA-Z0-9+.#-]{2,}", headline.lower()) if len(t) > 3][:8]
    rest = _norm(about + " " + " ".join(bullets))
    if hl_tokens:
        consistent = sum(1 for t in hl_tokens if t in rest) / len(hl_tokens)
    else:
        consistent = 0.4
    consistency = int(round(100 * consistent))

    overall = int(
        round(
            0.22 * keyword_score
            + 0.18 * role_alignment
            + 0.14 * quantification
            + 0.12 * clarity
            + 0.14 * impact
            + 0.12 * completeness
            + 0.08 * consistency
        )
    )

    weak = []
    if keyword_score < 60:
        weak.append("keyword_match")
    if role_alignment < 60:
        weak.append("role_alignment")
    if quantification < 50:
        weak.append("quantification")
    if clarity < 60:
        weak.append("clarity")
    if impact < 55:
        weak.append("impact")
    if completeness < 70:
        weak.append("completeness")
    if consistency < 55:
        weak.append("consistency")

    checklist = []
    if must_missing[:8]:
        checklist.append(
            {
                "id": "missing_keywords",
                "label": "Add recruiter-search keywords",
                "detail": ", ".join(must_missing[:8]),
                "severity": "high",
            }
        )
    if not title_found:
        checklist.append(
            {
                "id": "title_in_headline",
                "label": "Put a searchable role title in your headline",
                "detail": "Try: " + " · ".join(role["search_titles"][:3]),
                "severity": "high",
            }
        )
    if quantification < 50:
        checklist.append(
            {
                "id": "add_metrics",
                "label": "Add measurable outcomes to experience bullets",
                "detail": "%, latency, cost, uptime, headcount, traffic, time saved",
                "severity": "high",
            }
        )
    if not checks["skills"] or len(skills) < 8:
        checklist.append(
            {
                "id": "skills_count",
                "label": "Expand Skills (aim for 8–15 role-relevant items)",
                "detail": ", ".join((must_missing + nice_missing)[:10]),
                "severity": "medium",
            }
        )
    if not checks["open_to_work"]:
        checklist.append(
            {
                "id": "open_to_work",
                "label": "Fill Open to Work / job preferences",
                "detail": "Titles, locations, start timing — helps recruiter filters",
                "severity": "medium",
            }
        )
    if fluff:
        checklist.append(
            {
                "id": "cut_fluff",
                "label": "Cut generic buzzwords",
                "detail": "Replace soft claims with concrete systems and outcomes",
                "severity": "low",
            }
        )

    return {
        "role_id": role["id"],
        "role_label": role["label"],
        "overall": overall,
        "dimensions": {
            "keyword_match": keyword_score,
            "role_alignment": role_alignment,
            "quantification": quantification,
            "clarity": clarity,
            "impact": impact,
            "completeness": completeness,
            "consistency": consistency,
        },
        "weak_areas": weak,
        "found_keywords": must_found + [k for k in nice_found if k not in must_found],
        "missing_keywords": must_missing,
        "missing_nice_keywords": nice_missing[:12],
        "likely_recruiter_searches": role["search_titles"][:6],
        "title_hits": title_found,
        "checklist": checklist,
        "section_presence": checks,
        "mode": "heuristic",
    }
