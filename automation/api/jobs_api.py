"""Shared API job serialization with enrichment."""

from __future__ import annotations

from typing import Any

from store.enrich import (
    backfill_missing_metadata,
    enrich_job_dict,
    is_placeholder,
    persist_resolved_job,
    resolve_job_from_url,
)

from store.queries import (
    APPROVED_ONLY as _APPROVED_ONLY,
    LATEST_EVAL_JOIN,
    MIN_FIT_ONLY as _MIN_FIT_ONLY,
    NO_EVAL_ARTIFACTS as _NO_EVAL_ARTIFACTS,
    RELEVANT_ONLY as _RELEVANT_ONLY,
    min_fit_threshold,
)

_EVALUATED_PIPELINE = ("evaluated", "approved", "submitted")

_INBOX_PIPELINE = ("pending", "evaluated", "approved")

# List views omit jd_text — full JD is loaded on GET /jobs/{id} only.
# skills / experience come from metadata_json (Naukri/Apify enrichment).
_LIST_JOB_COLUMNS = """
    j.id, j.url, j.source, j.company, j.title, j.location, j.salary,
    j.company_email, j.fit_score, j.fit_reason, j.status, j.discovered_at, j.notes,
    j.created_at, j.updated_at,
    COALESCE(json_extract(j.metadata_json, '$.discovery_relevance'), 'relevant') AS discovery_relevance,
    json_extract(j.metadata_json, '$.skills') AS skills_json,
    json_extract(j.metadata_json, '$.experience') AS experience
"""


def apply_channel_for(job: dict) -> str:
    """How this job gets applied to: email (has company_email) | form (has URL) | manual."""
    if (job.get("company_email") or "").strip():
        return "email"
    if (job.get("url") or "").strip():
        return "form"
    return "manual"


def dedupe_skills(items: list[Any], limit: int = 20) -> list[str]:
    """Unique skills, case-insensitive, first spelling wins.

    Boards repeat skills ("Python" in both the preferred and other lists), and
    the UI keys skill chips by their label — duplicates crash the render.
    """
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        skill = str(item).strip()
        if not skill:
            continue
        key = skill.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(skill)
        if len(out) >= limit:
            break
    return out


def _parse_skills(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return dedupe_skills(raw)
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return []
        # SQLite json_extract returns a JSON string for arrays
        if s.startswith("["):
            try:
                import json

                parsed = json.loads(s)
                if isinstance(parsed, list):
                    return dedupe_skills(parsed)
            except Exception:
                pass
        return dedupe_skills(s.split(","))
    return []


def _row_to_job_dict(row, *, slim: bool = False) -> dict[str, Any]:
    job = enrich_job_dict(dict(row))
    job["apply_channel"] = apply_channel_for(job)
    skills_raw = job.pop("skills_json", None)
    if "skills" not in job or not job.get("skills"):
        job["skills"] = _parse_skills(skills_raw)
    if job.get("experience") is None:
        job["experience"] = ""
    else:
        job["experience"] = str(job.get("experience") or "")
    if slim:
        job.pop("jd_text", None)
        job.pop("eval_result_json", None)
        job.pop("result_json", None)
        job.pop("metadata_json", None)
    return job


def fetch_jobs(
    conn,
    *,
    status: str = "inbox",
    limit: int = 100,
    offset: int = 0,
    resolve_missing: bool = False,
    slim: bool = True,
    relevance: str = "relevant",
) -> list[dict[str, Any]]:
    st = (status or "inbox").lower()
    job_cols = _LIST_JOB_COLUMNS if slim else "j.*"
    # relevance="all" reveals off-target finds; default hides them.
    show_all = (relevance or "relevant").lower() == "all"
    rel = "" if show_all else _RELEVANT_ONLY
    fit = "" if show_all else _MIN_FIT_ONLY
    min_fit = min_fit_threshold()

    if st == "inbox":
        placeholders = ",".join("?" * len(_INBOX_PIPELINE))
        query = f"""
            SELECT {job_cols}, p.status AS pipeline_status,
                   ev.eval_score, ev.eval_legitimacy, ev.result_json AS eval_result_json
            FROM pipeline p
            JOIN jobs j ON j.id = p.job_id
            {LATEST_EVAL_JOIN}
            WHERE p.status IN ({placeholders}) {rel} {fit} {_NO_EVAL_ARTIFACTS} {_APPROVED_ONLY}
            ORDER BY p.added_at DESC
            LIMIT ? OFFSET ?
        """
        params_list: list[Any] = [*_INBOX_PIPELINE]
        if not show_all:
            params_list.append(min_fit)
        params_list.extend([limit, offset])
        params = tuple(params_list)
    elif st == "pending":
        query = f"""
            SELECT {job_cols}, p.status AS pipeline_status,
                   ev.eval_score, ev.eval_legitimacy, ev.result_json AS eval_result_json
            FROM pipeline p
            JOIN jobs j ON j.id = p.job_id
            {LATEST_EVAL_JOIN}
            WHERE p.status = 'pending' {rel} {fit} {_NO_EVAL_ARTIFACTS} {_APPROVED_ONLY}
            ORDER BY p.added_at DESC
            LIMIT ? OFFSET ?
        """
        params_list = []
        if not show_all:
            params_list.append(min_fit)
        params_list.extend([limit, offset])
        params = tuple(params_list)
    elif st == "approved":
        # The apply runner's queue. It used to ask for "evaluated" and filter the
        # response down to approved rows, but that response is one page — so an
        # approved job sitting past row 100 was never offered for apply.
        query = f"""
            SELECT {job_cols}, p.status AS pipeline_status,
                   ev.eval_score, ev.eval_legitimacy, ev.result_json AS eval_result_json
            FROM pipeline p
            JOIN jobs j ON j.id = p.job_id
            {LATEST_EVAL_JOIN}
            WHERE p.status = 'approved' {rel} {fit} {_NO_EVAL_ARTIFACTS} {_APPROVED_ONLY}
            ORDER BY p.added_at DESC
            LIMIT ? OFFSET ?
        """
        params_list = []
        if not show_all:
            params_list.append(min_fit)
        params_list.extend([limit, offset])
        params = tuple(params_list)
    elif st == "evaluated":
        placeholders = ",".join("?" * len(_EVALUATED_PIPELINE))
        query = f"""
            SELECT {job_cols}, p.status AS pipeline_status,
                   ev.eval_score, ev.eval_legitimacy, ev.result_json AS eval_result_json
            FROM pipeline p
            JOIN jobs j ON j.id = p.job_id
            {LATEST_EVAL_JOIN}
            WHERE p.status IN ({placeholders}) {rel} {fit} {_NO_EVAL_ARTIFACTS} {_APPROVED_ONLY}
            ORDER BY p.added_at DESC
            LIMIT ? OFFSET ?
        """
        params_list = [*_EVALUATED_PIPELINE]
        if not show_all:
            params_list.append(min_fit)
        params_list.extend([limit, offset])
        params = tuple(params_list)
    else:
        query = f"""
            SELECT {job_cols}, ev.eval_score, ev.eval_legitimacy, ev.result_json AS eval_result_json
            FROM jobs j
            {LATEST_EVAL_JOIN}
            WHERE j.source != 'eval'
              {_APPROVED_ONLY}
            ORDER BY j.updated_at DESC
            LIMIT ? OFFSET ?
        """
        params = (limit, offset)

    rows = conn.execute(query, params).fetchall()

    if resolve_missing and rows:
        backfill_missing_metadata(conn, [dict(r) for r in rows], max_jobs=min(10, len(rows)))
        rows = conn.execute(query, params).fetchall()

    return [_row_to_job_dict(r, slim=slim) for r in rows]


def fetch_job(conn, job_id: str, *, resolve_missing: bool = False) -> dict[str, Any] | None:
    row = conn.execute(
        f"""
        SELECT j.*, p.status AS pipeline_status,
               ev.eval_score, ev.eval_legitimacy, ev.result_json AS eval_result_json
        FROM jobs j
        LEFT JOIN pipeline p ON p.job_id = j.id
        {LATEST_EVAL_JOIN}
        WHERE j.id = ?
        """,
        (job_id,),
    ).fetchone()
    if not row:
        return None
    if resolve_missing:
        backfill_missing_metadata(conn, [dict(row)], max_jobs=1)
        row = conn.execute(
            f"""
            SELECT j.*, p.status AS pipeline_status,
                   ev.eval_score, ev.eval_legitimacy, ev.result_json AS eval_result_json
            FROM jobs j
            LEFT JOIN pipeline p ON p.job_id = j.id
            {LATEST_EVAL_JOIN}
            WHERE j.id = ?
            """,
            (job_id,),
        ).fetchone()
    return _row_to_job_dict(row, slim=False)


def prepare_job_for_eval(row: dict) -> tuple[str, str, str, str]:
    """Return (jd_text, company, title, url) with optional ATS resolve."""
    job_id = row["id"]
    url = row.get("url") or ""
    company = row.get("company") or ""
    title = row.get("title") or ""
    jd = row.get("jd_text") or ""

    needs_resolve = (
        not jd.strip()
        or is_placeholder(company)
        or is_placeholder(title)
    )
    if needs_resolve and url:
        resolved = resolve_job_from_url(url)
        if resolved:
            persist_resolved_job(job_id, resolved)
            if not jd.strip():
                jd = resolved.get("jd_snippet") or resolved.get("description") or ""
            if is_placeholder(company):
                company = resolved.get("company") or company
            if is_placeholder(title):
                title = resolved.get("title") or title

    if not jd.strip():
        jd = f"Job posting at {company or 'company'} for {title or 'role'}. URL: {url}"

    return jd, company, title, url
