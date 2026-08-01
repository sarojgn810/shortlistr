"""Persist / load contact-resolution rows (schema v16)."""

from __future__ import annotations

import json
import re
from typing import Any

from store import db as store


def _name_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower())


def upsert_company(
    name: str,
    *,
    email_domain: str = "",
    website_domain: str = "",
    mx_provider: str = "",
    is_catch_all: int | None = None,
    country: str = "",
) -> int:
    key = _name_key(name)
    if not key:
        key = "unknown"
    with store.db() as conn:
        row = conn.execute(
            "SELECT company_id FROM cr_company WHERE name_key = ?", (key,)
        ).fetchone()
        if row:
            cid = int(row["company_id"])
            conn.execute(
                """
                UPDATE cr_company SET
                    name = ?,
                    email_domain = COALESCE(NULLIF(?, ''), email_domain),
                    website_domain = COALESCE(NULLIF(?, ''), website_domain),
                    mx_provider = COALESCE(NULLIF(?, ''), mx_provider),
                    is_catch_all = COALESCE(?, is_catch_all),
                    country = COALESCE(NULLIF(?, ''), country),
                    updated_at = datetime('now')
                WHERE company_id = ?
                """,
                (
                    name.strip() or key,
                    email_domain,
                    website_domain,
                    mx_provider,
                    is_catch_all,
                    country,
                    cid,
                ),
            )
            return cid
        cur = conn.execute(
            """
            INSERT INTO cr_company
                (name, name_key, email_domain, website_domain, mx_provider, is_catch_all, country)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name.strip() or key,
                key,
                email_domain or None,
                website_domain or None,
                mx_provider or None,
                is_catch_all,
                country or None,
            ),
        )
        return int(cur.lastrowid)


def save_pattern(
    company_id: int,
    pattern: str,
    *,
    confidence: float,
    sample_count: int,
    source_list: str = "",
) -> None:
    with store.db() as conn:
        conn.execute(
            """
            INSERT INTO cr_email_pattern
                (company_id, pattern, confidence, sample_count, source_list, learned_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(company_id, pattern) DO UPDATE SET
                confidence = excluded.confidence,
                sample_count = excluded.sample_count,
                source_list = excluded.source_list,
                learned_at = datetime('now')
            """,
            (company_id, pattern, confidence, sample_count, source_list),
        )


def get_patterns(company_id: int) -> list[dict[str, Any]]:
    with store.db() as conn:
        rows = conn.execute(
            """
            SELECT pattern, confidence, sample_count, source_list
            FROM cr_email_pattern WHERE company_id = ?
            ORDER BY confidence DESC, sample_count DESC
            """,
            (company_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def insert_person(
    *,
    company_id: int | None,
    job_id: str,
    full_name: str,
    first_name: str = "",
    last_name: str = "",
    title: str = "",
    seniority_rank: int | None = None,
    linkedin_url: str = "",
    github_login: str = "",
    source: str = "",
    discovery_conf: float = 0.0,
) -> int:
    with store.db() as conn:
        cur = conn.execute(
            """
            INSERT INTO cr_person (
                company_id, job_id, full_name, first_name, last_name, title,
                seniority_rank, linkedin_url, github_login, source, discovery_conf
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                company_id,
                job_id,
                full_name,
                first_name,
                last_name,
                title,
                seniority_rank,
                linkedin_url,
                github_login,
                source,
                discovery_conf,
            ),
        )
        return int(cur.lastrowid)


def insert_email(
    *,
    person_id: int,
    job_id: str,
    email: str,
    gen_method: str,
    pattern_conf: float = 0.0,
    verify_status: str = "unknown",
    verify_source: str = "",
    source_count: int = 1,
    final_score: float = 0.0,
    decision: str = "REVIEW",
) -> int:
    with store.db() as conn:
        cur = conn.execute(
            """
            INSERT INTO cr_email_candidate (
                person_id, job_id, email, gen_method, pattern_conf,
                verify_status, verify_source, source_count, final_score, decision
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                person_id,
                job_id,
                email,
                gen_method,
                pattern_conf,
                verify_status,
                verify_source,
                source_count,
                final_score,
                decision,
            ),
        )
        return int(cur.lastrowid)


def add_evidence(
    entity_type: str,
    entity_id: int,
    kind: str,
    value: str = "",
    url: str = "",
) -> None:
    with store.db() as conn:
        conn.execute(
            """
            INSERT INTO cr_evidence (entity_type, entity_id, kind, value, url)
            VALUES (?, ?, ?, ?, ?)
            """,
            (entity_type, entity_id, kind, value[:2000], url[:1000]),
        )


def clear_job_resolution(job_id: str) -> None:
    """Drop prior people/emails for a job before re-resolve (keep company/patterns)."""
    with store.db() as conn:
        people = conn.execute(
            "SELECT person_id FROM cr_person WHERE job_id = ?", (job_id,)
        ).fetchall()
        pids = [int(r["person_id"]) for r in people]
        if pids:
            placeholders = ",".join("?" * len(pids))
            email_ids = [
                int(r["email_id"])
                for r in conn.execute(
                    f"SELECT email_id FROM cr_email_candidate WHERE person_id IN ({placeholders})",
                    pids,
                ).fetchall()
            ]
            if email_ids:
                eph = ",".join("?" * len(email_ids))
                conn.execute(
                    f"DELETE FROM cr_evidence WHERE entity_type = 'email' AND entity_id IN ({eph})",
                    email_ids,
                )
            conn.execute(
                f"DELETE FROM cr_email_candidate WHERE person_id IN ({placeholders})",
                pids,
            )
            conn.execute(
                f"DELETE FROM cr_evidence WHERE entity_type = 'person' AND entity_id IN ({placeholders})",
                pids,
            )
            conn.execute(
                f"DELETE FROM cr_person WHERE person_id IN ({placeholders})",
                pids,
            )
        conn.execute("DELETE FROM cr_email_candidate WHERE job_id = ?", (job_id,))
        conn.execute("DELETE FROM cr_job_resolution WHERE job_id = ?", (job_id,))


def save_job_resolution(
    job_id: str,
    *,
    company_id: int | None,
    status: str,
    best_person_id: int | None,
    best_email_id: int | None,
    summary: dict[str, Any],
) -> None:
    with store.db() as conn:
        conn.execute(
            """
            INSERT INTO cr_job_resolution
                (job_id, company_id, status, best_person_id, best_email_id, summary_json, resolved_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(job_id) DO UPDATE SET
                company_id = excluded.company_id,
                status = excluded.status,
                best_person_id = excluded.best_person_id,
                best_email_id = excluded.best_email_id,
                summary_json = excluded.summary_json,
                resolved_at = datetime('now')
            """,
            (
                job_id,
                company_id,
                status,
                best_person_id,
                best_email_id,
                json.dumps(summary),
            ),
        )


def get_job_resolution(job_id: str) -> dict[str, Any] | None:
    with store.db() as conn:
        row = conn.execute(
            "SELECT * FROM cr_job_resolution WHERE job_id = ?", (job_id,)
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        try:
            d["summary"] = json.loads(d.get("summary_json") or "{}")
        except Exception:
            d["summary"] = {}
        people = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM cr_person WHERE job_id = ? ORDER BY discovery_conf DESC",
                (job_id,),
            ).fetchall()
        ]
        emails = [
            dict(r)
            for r in conn.execute(
                """
                SELECT e.*, p.full_name AS person_name, p.linkedin_url AS person_linkedin
                FROM cr_email_candidate e
                LEFT JOIN cr_person p ON p.person_id = e.person_id
                WHERE e.job_id = ?
                ORDER BY e.final_score DESC
                """,
                (job_id,),
            ).fetchall()
        ]
        for e in emails:
            if not e.get("linkedin_url") and e.get("person_linkedin"):
                e["linkedin_url"] = e["person_linkedin"]
        company = None
        if d.get("company_id"):
            crow = conn.execute(
                "SELECT * FROM cr_company WHERE company_id = ?",
                (d["company_id"],),
            ).fetchone()
            company = dict(crow) if crow else None
        evidence = []
        for p in people:
            evidence.extend(
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM cr_evidence WHERE entity_type = 'person' AND entity_id = ?",
                    (p["person_id"],),
                ).fetchall()
            )
        d["people"] = people
        d["emails"] = emails
        d["company"] = company
        d["evidence"] = evidence
        return d
