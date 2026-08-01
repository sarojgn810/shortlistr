"""Shared SQL fragments for job + eval queries."""

from __future__ import annotations

# Minimum JD length worth showing a candidate — below this the posting is a stub
# and both matching and tailoring produce noise.
MIN_JD_CHARS = 200


def fetch_candidate_jobs(
    conn,
    *,
    locations: list[str] | None = None,
    remote_ok: bool = True,
    limit: int = 400,
) -> list:
    """Live scraped jobs for candidate matching.

    Deliberately NOT jobs_api.fetch_jobs(status="all"): that catch-all skips the
    pipeline join, is capped at 100 by its caller, and drops relevance filters.

    Location narrowing happens here so the Python scorer never tokenizes the whole
    corpus. `locations` are free-text terms (city or country); an empty list means
    no location constraint.
    """
    where = [
        "archived_at IS NULL",
        "source != 'eval'",
        # NULL = scraped by us (auto-trusted). Anything a user submitted must be
        # approved by an admin before a candidate ever sees it.
        "(review_status IS NULL OR review_status = 'approved')",
        "jd_text IS NOT NULL",
        # The length floor screens out stub SCRAPED postings. Referrer-attested
        # roles are legitimately terse (a title, a location, a req id) because a
        # real employee vouched for them rather than a crawler finding them.
        "(source = 'referrer' OR length(jd_text) > ?)",
    ]
    params: list = [MIN_JD_CHARS]

    terms = [t.strip() for t in (locations or []) if t and t.strip()]
    if terms:
        clauses = ["LOWER(location) LIKE ?" for _ in terms]
        params.extend(f"%{t.lower()}%" for t in terms)
        if remote_ok:
            clauses.append("LOWER(location) LIKE '%remote%'")
        where.append("(" + " OR ".join(clauses) + ")")

    params.append(limit)
    return conn.execute(
        f"SELECT id, company, title, url, location, source, jd_text, discovered_at, "  # noqa: S608
        # company stays for matching; the confidentiality pair is display only.
        f"       referrer_phone, company_confidential, company_hint "
        f"FROM jobs WHERE {' AND '.join(where)} "
        f"ORDER BY discovered_at DESC, updated_at DESC LIMIT ?",
        params,
    ).fetchall()


def fetch_jobs_for_review(conn, *, status: str = "pending", limit: int = 100) -> list:
    """User-submitted jobs awaiting an admin decision."""
    return conn.execute(
        "SELECT id, company, title, url, location, submitted_by, referrer_phone, "
        "       discovered_at, jd_text "
        "FROM jobs WHERE review_status = ? ORDER BY discovered_at DESC, id LIMIT ?",
        (status, limit),
    ).fetchall()

# Off-target finds stay in the DB (tagged, reachable via "All") but must not
# reach a default view. Discover and the tracker board have to agree on what
# "on target" means, or the board silently reintroduces everything Discover
# filtered out. Both fragments assume the jobs table is aliased `j`.
RELEVANT_ONLY = (
    "AND COALESCE(json_extract(j.metadata_json, '$.discovery_relevance'), 'relevant') "
    "!= 'off_target'"
)
MIN_FIT_ONLY = "AND COALESCE(j.fit_score, 0) >= ?"

DEFAULT_MIN_FIT = 40


def min_fit_threshold() -> int:
    """Configured fit floor for default job views.

    0 is a legitimate setting meaning "show everything", so only a missing or
    unparseable value falls back to the default. A truthiness check here reads
    a deliberate 0 as unset and silently re-imposes the floor.
    """
    import config as cfg

    value = getattr(cfg, "MIN_FIT_SCORE", None)
    if value is None:
        return DEFAULT_MIN_FIT
    try:
        return int(value)
    except (TypeError, ValueError):
        return DEFAULT_MIN_FIT

# Evaluation creates job rows with source='eval' to attach results; these are
# artifacts, not discovered jobs.
NO_EVAL_ARTIFACTS = "AND j.source != 'eval'"

# NULL review_status = we scraped it ourselves, which is trusted. User-submitted
# jobs wait for an admin decision before surfacing.
APPROVED_ONLY = "AND (j.review_status IS NULL OR j.review_status = 'approved')"

LATEST_EVAL_JOIN = """
LEFT JOIN (
    SELECT job_id, score AS eval_score, legitimacy AS eval_legitimacy, result_json
    FROM eval_results e1
    WHERE id = (
        SELECT id FROM eval_results e2
        WHERE e2.job_id = e1.job_id ORDER BY id DESC LIMIT 1
    )
) ev ON ev.job_id = j.id
"""

# List views: score + legitimacy + tiny mode flags only — never full result_json.
# json_extract on large blobs was a major Inbox latency / crash source.
LATEST_EVAL_JOIN_SLIM = """
LEFT JOIN (
    SELECT job_id,
           score AS eval_score,
           legitimacy AS eval_legitimacy,
           COALESCE(
             json_extract(result_json, '$.eval_mode'),
             json_extract(result_json, '$.template_only')
           ) AS eval_mode_flag
    FROM eval_results e1
    WHERE id = (
        SELECT id FROM eval_results e2
        WHERE e2.job_id = e1.job_id ORDER BY id DESC LIMIT 1
    )
) ev ON ev.job_id = j.id
"""

LATEST_EVAL_JOIN_ON_APPLICATIONS = """
LEFT JOIN (
    SELECT job_id, score AS eval_score, legitimacy AS eval_legitimacy, result_json
    FROM eval_results e1
    WHERE id = (
        SELECT id FROM eval_results e2
        WHERE e2.job_id = e1.job_id ORDER BY id DESC LIMIT 1
    )
) ev ON ev.job_id = a.job_id
"""
