"""Tracker board — pipeline status + application status unified columns."""

from __future__ import annotations

from typing import Any

from store.queries import (
    APPROVED_ONLY,
    LATEST_EVAL_JOIN,
    MIN_FIT_ONLY,
    NO_EVAL_ARTIFACTS,
    RELEVANT_ONLY,
    min_fit_threshold,
)


def _column_for_row(pipeline_status: str, application_status: str | None) -> str:
    app = (application_status or "").lower()
    pipe = (pipeline_status or "pending").lower()

    if app in ("responded", "interview", "offer"):
        return "active"
    if pipe == "submitted" or app == "applied":
        return "submitted"
    if pipe == "approved":
        return "approved"
    if pipe in ("skipped",):
        return "skipped"
    return "review"


def fetch_tracker_board(
    conn, *, limit: int = 200, relevance: str = "relevant"
) -> dict[str, Any]:
    show_all = (relevance or "relevant").lower() == "all"

    # The review column is the same judgment queue as Discover, so it takes the
    # same targeting gate. Without it the board re-listed every off-target find
    # the inbox had already filtered out.
    #
    # The gate covers review candidates only: once a job has been approved,
    # submitted or applied to, the user's decision outranks current targeting,
    # and retargeting must never make in-flight applications disappear.
    if show_all:
        targeting = ""
        gate_params: list[Any] = []
    else:
        targeting = f"""
        AND (
            p.status IN ('approved', 'submitted')
            OR a.status IN ('applied', 'responded', 'interview', 'offer')
            OR (1 = 1 {RELEVANT_ONLY} {MIN_FIT_ONLY})
        )
        """
        gate_params = [min_fit_threshold()]

    # Surface downstream stages first. The review column can have thousands of
    # rows; ordering by added_at alone pushes the handful of approved/submitted/
    # active jobs (added early) past the LIMIT, so they vanished from the board.
    # Prioritising non-review statuses guarantees they always appear, then the
    # remaining budget fills with the most-recent review items.
    rows = conn.execute(
        f"""
        SELECT j.id, j.company, j.title, j.url, j.location, j.salary, j.source,
               j.discovered_at, j.updated_at,
               p.status AS pipeline_status, p.added_at AS pipeline_added_at,
               a.status AS application_status, a.score, a.applied_date, a.id AS application_id,
               ev.eval_score, ev.eval_legitimacy,
               json_extract(j.metadata_json, '$.skills') AS skills_json,
               json_extract(j.metadata_json, '$.experience') AS experience
        FROM pipeline p
        JOIN jobs j ON j.id = p.job_id
        LEFT JOIN applications a ON a.id = (
            SELECT id FROM applications WHERE job_id = j.id ORDER BY id DESC LIMIT 1
        )
        {LATEST_EVAL_JOIN}
        WHERE p.status != 'skipped'
          {NO_EVAL_ARTIFACTS} {APPROVED_ONLY}
          {targeting}
        ORDER BY
            CASE
                WHEN p.status IN ('approved', 'submitted') THEN 0
                WHEN a.status IN ('applied', 'responded', 'interview', 'offer') THEN 0
                ELSE 1
            END,
            p.added_at DESC
        LIMIT ?
        """,
        (*gate_params, limit),
    ).fetchall()

    columns: dict[str, list[dict[str, Any]]] = {
        "review": [],
        "approved": [],
        "submitted": [],
        "active": [],
    }

    def _skills(raw: Any) -> list[str]:
        from api.jobs_api import dedupe_skills

        if raw is None:
            return []
        if isinstance(raw, list):
            return dedupe_skills(raw, limit=8)
        if isinstance(raw, str) and raw.startswith("["):
            try:
                import json

                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return dedupe_skills(parsed, limit=8)
            except Exception:
                return []
        return []

    for row in rows:
        d = dict(row)
        col = _column_for_row(
            str(d.get("pipeline_status") or ""),
            d.get("application_status"),
        )
        if col == "skipped":
            continue
        score = d.get("eval_score")
        if score is None and d.get("score") is not None:
            score = d["score"]
        columns[col].append(
            {
                "job_id": d["id"],
                "company": d.get("company"),
                "title": d.get("title"),
                "url": d.get("url"),
                "location": d.get("location"),
                "salary": d.get("salary"),
                "source": d.get("source"),
                "skills": _skills(d.get("skills_json")),
                "experience": d.get("experience") or "",
                "pipeline_status": d.get("pipeline_status"),
                "application_status": d.get("application_status"),
                "score": float(score) if score is not None else None,
                "legitimacy": d.get("eval_legitimacy"),
                "applied_date": d.get("applied_date"),
                "application_id": d.get("application_id"),
                "updated_at": d.get("updated_at") or d.get("pipeline_added_at"),
            }
        )

    return {
        "columns": columns,
        "counts": {k: len(v) for k, v in columns.items()},
    }
