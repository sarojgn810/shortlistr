"""
Job Relevance Filter
Scores each job posting against the candidate profile and returns True only
for strong fits. Applied before any email or auto-apply action.

Filter thresholds (remote_strict, salary floors, deal_breakers) come from
config/profile.yml via config.py. Titles and skills come from the live profile /
résumé — never from an author-specific hardcoded stack.
"""

from __future__ import annotations

import logging
import os
import re

import config as _cfg

logger = logging.getLogger(__name__)

REMOTE_SIGNALS = [
    "remote", "work from home", "wfh", "work from anywhere",
    "anywhere", "worldwide", "fully remote", "100% remote",
    "distributed", "virtual",
]

_INR_PATTERN = re.compile(
    r"(?:₹|rs\.?|inr)\s*(\d+(?:\.\d+)?)\s*(?:[-–to]+\s*(?:₹|rs\.?|inr)?\s*(\d+(?:\.\d+)?))?\s*(lpa|lakh|lac|l\b)",
    re.IGNORECASE,
)
_USD_PATTERN = re.compile(
    r"\$\s*(\d{2,3}(?:,\d{3})*(?:\.\d+)?)\s*(?:k|000)?\s*(?:[-–to]+\s*\$?\s*(\d{2,3}(?:,\d{3})*(?:\.\d+)?)\s*(?:k|000)?)?(?:\s*/?\s*(?:year|yr|annual|pa))?",
    re.IGNORECASE,
)

# Roles that are almost never the user's target; still skipped unless the user
# explicitly put the same phrase in their target_titles.
_ALWAYS_DISQUALIFY = [
    "recruiter", "hr ", "talent acquisition",
    "10+ years", "12+ years", "15+ years", "15 years", "12 years of experience",
    "15 years of experience", "20 years", "20+ years",
]

SKILL_THRESHOLD = 2
SENIORITY_SKIP = ["junior ", "entry level", "entry-level", "associate ", "intern ", "trainee "]

# Atomic tech tokens used for JD overlap. Résumé skills sections are often
# category blobs ("SRE & Reliability SLO / SLI / Error Budgets"), so matching
# the whole phrase against a JD never hits. We mine these tokens instead.
_TECH_TOKENS = [
    "kubernetes", "k8s", "aws", "gcp", "azure", "terraform", "ansible",
    "prometheus", "grafana", "datadog", "splunk", "new relic", "opentelemetry",
    "python", "golang", "docker", "helm", "linux", "jenkins", "github actions",
    "argocd", "gitops", "observability", "slo", "sli", "sla", "incident",
    "on-call", "oncall", "ci/cd", "cicd", "kafka", "redis", "postgres",
    "postgresql", "sql", "java", "bash", "shell", "elk", "elasticsearch",
    "istio", "service mesh", "chaos", "runbook", "pagerduty", "cloudwatch",
    "lambda", "eks", "ecs", "mlops", "aiops", "rag", "llm", "openai",
]


def core_titles() -> list[str]:
    """Titles worth scoring — always from live SEARCH_KEYWORDS (profile)."""
    return [t.lower() for t in (_cfg.SEARCH_KEYWORDS or [])]


def skill_signals() -> list[str]:
    """Atomic skills mined from the résumé for JD overlap scoring.

    Prefer known tech tokens found in the skills (and summary) text over raw
    category phrases. Falls back to short split tokens when nothing known hits.
    """
    try:
        from config import CV_MD_PATH
        from cv.parser import parse_cv_markdown

        if not CV_MD_PATH or not os.path.isfile(CV_MD_PATH):
            return []
        md = open(CV_MD_PATH, encoding="utf-8").read()
        sections = parse_cv_markdown(md)
        blob = " ".join(
            [
                getattr(sections, "skills", "") or "",
                getattr(sections, "competencies", "") or "",
                getattr(sections, "summary", "") or "",
            ]
        ).lower()
        if not blob.strip():
            return []

        found: list[str] = []
        for tok in _TECH_TOKENS:
            # Word-ish boundary so "go" doesn't match "golang" twice wrongly,
            # and short tokens like "sli" don't match inside longer words.
            if re.search(rf"(?<![a-z0-9]){re.escape(tok)}(?![a-z0-9])", blob):
                if tok not in found:
                    found.append(tok)
        if found:
            return found[:40]

        # Fallback: split categories into short fragments.
        parts = re.split(r"[,;/\n•·|&]+", blob)
        out: list[str] = []
        for p in parts:
            s = re.sub(r"\s+", " ", p).strip().lower()
            if 2 <= len(s) <= 40 and s not in out:
                out.append(s)
        return out[:40]
    except Exception:
        return []


def disqualify_phrases() -> list[str]:
    """Disqualifiers minus anything that overlaps the user's own target titles."""
    titles = core_titles()
    deal = [d.lower() for d in (_cfg.DEAL_BREAKERS or []) if d]
    raw = _ALWAYS_DISQUALIFY + deal

    def _conflicts(phrase: str) -> bool:
        for t in titles:
            if t and (t in phrase or phrase in t):
                return True
        return False

    return [p for p in raw if not _conflicts(p)]


def _clean(text: str) -> str:
    return text.lower().strip()


def _token_in_text(token: str, text: str) -> bool:
    """Substring match with word boundaries for short / ambiguous tokens."""
    tok = (token or "").lower().strip()
    hay = text or ""
    if not tok or not hay:
        return False
    if len(tok) <= 4 or tok in {"java", "bash", "helm", "linux", "chaos", "redis", "kafka"}:
        return bool(re.search(rf"(?<![a-z0-9]){re.escape(tok)}(?![a-z0-9])", hay))
    return tok in hay


def score_job(job: dict) -> dict:
    """
    Returns the job dict with two new keys:
      fit_score  : int  — higher = stronger fit
      fit_reason : str  — human-readable explanation
    """
    title = _clean(job.get("title", ""))
    jd = _clean(job.get("jd_snippet", "") or job.get("description", ""))
    full_text = f"{title} {jd}"

    reasons: list[str] = []
    score = 0
    titles = core_titles()

    # ── 1. Title must match profile targeting ────────────────────────────────
    if not titles:
        job["fit_score"] = 0
        job["fit_reason"] = "no target titles configured — complete onboarding"
        return job

    title_match = any(kw in title for kw in titles)
    if title_match:
        score += 40
        reasons.append("title match")
    else:
        job["fit_score"] = 0
        job["fit_reason"] = f"title mismatch: '{job.get('title', '')}'"
        return job

    # ── 2. Seniority check ───────────────────────────────────────────────────
    years_exp = int((_cfg.CANDIDATE or {}).get("years_exp", 0) or 0)
    if years_exp >= 3 and any(s in title for s in SENIORITY_SKIP):
        job["fit_score"] = 0
        job["fit_reason"] = f"junior/entry-level role: '{job.get('title', '')}'"
        return job

    # ── 3a. Strict remote check ──────────────────────────────────────────────
    if _cfg.REMOTE_STRICT:
        loc = _clean(
            job.get("location", "") + " " + job.get("jd_snippet", "") + " " + job.get("description", "")
        )
        if not any(sig in loc for sig in REMOTE_SIGNALS):
            job["fit_score"] = 0
            job["fit_reason"] = f"not explicitly remote (location: '{job.get('location', 'unspecified')}')"
            return job

    # ── 3b. Salary floor check ───────────────────────────────────────────────
    salary_text = _clean(
        job.get("salary", "") + " " + job.get("jd_snippet", "") + " " + job.get("description", "")
    )
    inr_match = _INR_PATTERN.search(salary_text)
    usd_match = _USD_PATTERN.search(salary_text)
    if inr_match:
        val = float(inr_match.group(1))
        if _cfg.MIN_SALARY_INR_LPA and val < _cfg.MIN_SALARY_INR_LPA:
            job["fit_score"] = 0
            job["fit_reason"] = f"salary below floor: ₹{val}L < ₹{_cfg.MIN_SALARY_INR_LPA}L"
            return job
    elif usd_match:
        raw = usd_match.group(1).replace(",", "")
        val = float(raw)
        if val < 1000:
            val *= 1000
        if _cfg.MIN_SALARY_USD and val < _cfg.MIN_SALARY_USD:
            job["fit_score"] = 0
            job["fit_reason"] = f"salary below floor: ${val:,.0f} < ${_cfg.MIN_SALARY_USD:,}"
            return job
    elif _cfg.SALARY_UNLISTED == "skip" and (_cfg.MIN_SALARY_INR_LPA or _cfg.MIN_SALARY_USD):
        job["fit_score"] = 0
        job["fit_reason"] = "salary not listed (salary_unlisted=skip)"
        return job

    # ── 3c. Disqualifying phrases (never fights the user's own titles) ───────
    for phrase in disqualify_phrases():
        if phrase in full_text:
            job["fit_score"] = 0
            job["fit_reason"] = f"disqualifier found: '{phrase}'"
            return job

    # ── 4. Skill overlap from résumé ─────────────────────────────────────────
    # Three honest cases:
    #   skills + JD text  → score overlap (and soft-penalize thin overlap)
    #   skills, no JD     → keep title/location score; say JD isn't fetched yet
    #   no skills         → title-only provisional bonus
    skills = skill_signals()
    if skills and jd:
        jd_signals = [s for s in skills if _token_in_text(s, jd)]
        skill_score = min(len(jd_signals) * 5, 40)
        score += skill_score
        if jd_signals:
            reasons.append(f"JD skills: {', '.join(jd_signals[:5])}")
        if len(jd_signals) < SKILL_THRESHOLD:
            job["fit_score"] = max(score - 20, 0)
            job["fit_reason"] = f"low skill overlap in JD ({len(jd_signals)} signals)"
            return job
    elif skills and not jd:
        # LinkedIn guest / thin aggregator cards often have title+location only.
        # Don't blame the résumé — and don't re-append "title match".
        score += 10
        reasons.append("JD not fetched yet")
    else:
        score += 10
        reasons.append("résumé skills not parsed yet")

    # ── 5. Location bonus from the user's preferred locations ────────────────
    loc = _clean(job.get("location", ""))
    loc_keywords = [lk.lower() for lk in (_cfg.LOCATION_KEYWORDS or [])]
    if loc_keywords and any(lk in loc for lk in loc_keywords):
        score += 10
        reasons.append("preferred location")
    elif any(sig in loc for sig in REMOTE_SIGNALS):
        score += 5
        reasons.append("remote location")

    # ── 6. Outcome-learned adjustment (bounded + transparent) ────────────────
    try:
        from outcomes.adapt import score_adjustment

        delta, why = score_adjustment(job)
        if delta:
            score += delta
            reasons.append(why)
    except Exception:
        pass

    job["fit_score"] = min(score, 100)
    reason = "; ".join(reasons) if reasons else "basic title match"
    try:
        from writing.sanitize import sanitize

        reason = sanitize(reason, mode="label")
    except Exception:
        pass
    job["fit_reason"] = reason
    return job


def is_strong_fit(job: dict, min_score: int | None = None) -> bool:
    """
    Returns True if job is a strong fit for the configured profile.
    min_score defaults to scoring.min_fit_score from profile.yml.
    """
    if min_score is None:
        min_score = _cfg.MIN_FIT_SCORE
    if "fit_score" not in job:
        job = score_job(job)
    return job["fit_score"] >= min_score


def filter_jobs(jobs: list, min_score: int | None = None) -> tuple:
    """
    Split jobs into (strong_fit_jobs, weak_fit_jobs).
    Logs a summary.
    """
    if min_score is None:
        min_score = _cfg.MIN_FIT_SCORE

    strong, weak = [], []
    for job in jobs:
        score_job(job)
        if is_strong_fit(job, min_score):
            strong.append(job)
        else:
            weak.append(job)

    logger.info(
        "Fit filter: %s strong / %s weak (min_score=%s)",
        len(strong),
        len(weak),
        min_score,
    )
    return strong, weak
