"""Optional LinkedIn jobs actor for the Apify board.

The default actor stays valig/linkedin-jobs-scraper. Set
SHORTLISTR_LINKEDIN_JOBS_ACTOR, or sources.apify.linkedin_actor, to
johnvc/linkedin-jobs-api to send a keyword body and keep job rows.
"""

from __future__ import annotations

from typing import Any

OPTIONAL_LINKEDIN_JOBS_ACTOR = "johnvc/linkedin-jobs-api"
LINKEDIN_JOBS_ACTOR_ENV = "SHORTLISTR_LINKEDIN_JOBS_ACTOR"
DEFAULT_LINKEDIN_JOBS_ACTOR = "valig/linkedin-jobs-scraper"
_OPTIONAL_IDS = {
    OPTIONAL_LINKEDIN_JOBS_ACTOR,
    "johnvc~linkedin-jobs-api",
}
_MAX_JOBS = 100


def resolve_linkedin_actor(cfg: dict[str, Any] | None, env_value: str | None) -> str:
    """Actor id for this run. The optional actor is used only on an exact match."""
    if (env_value or "").strip() in _OPTIONAL_IDS:
        return OPTIONAL_LINKEDIN_JOBS_ACTOR
    configured = str((cfg or {}).get("linkedin_actor") or "").strip()
    if configured in _OPTIONAL_IDS:
        return OPTIONAL_LINKEDIN_JOBS_ACTOR
    return configured or DEFAULT_LINKEDIN_JOBS_ACTOR


def _remote_only(location: str, wants_remote: bool) -> bool:
    loc = (location or "").strip().lower()
    has_city = bool(loc) and loc not in {"remote", "anywhere", "worldwide"}
    return bool(wants_remote) and not has_city


def optional_linkedin_jobs_input(
    title: str,
    location: str,
    *,
    limit: int,
    wants_remote: bool,
) -> dict[str, Any]:
    try:
        requested = int(limit)
    except (TypeError, ValueError):
        requested = 1
    max_jobs = min(_MAX_JOBS, max(1, requested))
    return {
        "keyword": title,
        "location": location,
        "maxJobs": max_jobs,
        "remote": _remote_only(location, wants_remote),
    }


def accept_linkedin_job_items(items: list[Any]) -> list[dict[str, Any]]:
    """Keep job rows and copy fields the existing record builder already reads."""
    kept: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict) or item.get("result_type") != "job":
            continue
        row = dict(item)
        if row.get("seniorityLevel") and not row.get("seniority"):
            row["seniority"] = row["seniorityLevel"]
        if not row.get("salary") and (row.get("salaryMin") or row.get("salaryMax")):
            if row.get("salaryMin") is not None:
                row["salary_min"] = row["salaryMin"]
            if row.get("salaryMax") is not None:
                row["salary_max"] = row["salaryMax"]
            if row.get("salaryCurrency"):
                row["currency"] = row["salaryCurrency"]
        kept.append(row)
    return kept
