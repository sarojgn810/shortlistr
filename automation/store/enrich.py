"""Enrich job records for API/UI — backfill company, title, JD from eval + URL."""

from __future__ import annotations

import json
import re
from typing import Any

from scrapers.html_text import html_to_plain

_PLACEHOLDERS = frozenset({"", "unknown", "untitled", "n/a", "na", "tbd", "?", "import"})
_BOILERPLATE_MARKERS = (
    "llm not configured",
    "template evaluation only",
    "verify posting manually",
    "configure ",
    "api_key",
    "job posting at ",
    "url: http",
)

# Slug → display name for common greenhouse board slugs
_COMPANY_ALIASES: dict[str, str] = {
    "datadoghq": "Datadog",
    "datadog": "Datadog",
    "sumologic": "Sumo Logic",
    "yugabyte": "Yugabyte",
    "kentik": "Kentik",
    "jobgether": "Jobgether",
}


def is_placeholder(value: str | None) -> bool:
    if value is None:
        return True
    return value.strip().lower() in _PLACEHOLDERS


def is_boilerplate_text(value: str | None) -> bool:
    if not value or not str(value).strip():
        return True
    lower = str(value).lower()
    return any(m in lower for m in _BOILERPLATE_MARKERS)


def prettify_company(name: str) -> str:
    """Turn ATS slug or raw name into a display label."""
    if not name or is_placeholder(name):
        return ""
    raw = name.strip()
    key = raw.lower().replace(" ", "").replace("-", "").replace("_", "")
    if key in _COMPANY_ALIASES:
        return _COMPANY_ALIASES[key]
    if key.endswith("hq"):
        base = key[:-2]
        if base in _COMPANY_ALIASES:
            return _COMPANY_ALIASES[base]
        if len(base) > 2:
            return base.title()

    if "-" in raw or "_" in raw:
        return _title_from_slug(raw)

    if raw.isupper() and len(raw) > 3:
        return raw.title()

    return raw.title() if raw.islower() else raw


def _title_from_slug(slug: str) -> str:
    return slug.replace("-", " ").replace("_", " ").strip().title()


def company_title_from_url(url: str) -> tuple[str, str]:
    """Best-effort company (and empty title) from ATS URL path — no network."""
    if not url:
        return "", ""
    try:
        from scrapers.ats_url_resolver import parse_ats_url

        parsed = parse_ats_url(url)
        if parsed:
            return prettify_company(parsed.slug), ""
    except Exception:
        pass

    m = re.search(r"(?:jobs|careers|boards)\.([a-z0-9-]+)\.", url, re.I)
    if m:
        return prettify_company(m.group(1)), ""
    return "", ""


def _from_eval_json(result_json: str | None) -> dict[str, Any]:
    if not result_json:
        return {}
    try:
        data = json.loads(result_json)
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def _clean_display_field(value: str) -> str:
    v = value.strip()
    if is_placeholder(v) or is_boilerplate_text(v):
        return ""
    return v


def enrich_job_dict(job: dict[str, Any]) -> dict[str, Any]:
    """Fill missing company/title/location/jd from eval JSON and URL parsing."""
    out = dict(job)
    company = _clean_display_field(str(out.get("company") or ""))
    title = _clean_display_field(str(out.get("title") or ""))
    location = str(out.get("location") or "").strip()
    jd_text = str(out.get("jd_text") or "").strip()
    url = str(out.get("url") or "").strip()

    eval_data = _from_eval_json(out.get("result_json"))
    if not eval_data and out.get("eval_result_json"):
        eval_data = _from_eval_json(out.get("eval_result_json"))

    blocks = eval_data.get("blocks") if isinstance(eval_data.get("blocks"), dict) else {}

    if not company:
        company = _clean_display_field(str(eval_data.get("company") or ""))
        company = prettify_company(company)
    if not title:
        title = _clean_display_field(
            str(eval_data.get("role") or eval_data.get("title") or "")
        )

    url_company, _ = company_title_from_url(url)
    if not company and url_company:
        company = url_company

    if not company and url:
        host = re.sub(r"^https?://", "", url).split("/")[0]
        if host and "greenhouse" not in host and "lever" not in host:
            seg = host.split(".")[0]
            if seg not in ("www", "jobs", "careers", "boards"):
                company = prettify_company(seg)

    if not title and jd_text and not is_boilerplate_text(jd_text):
        title = _extract_title_from_jd(jd_text)

    out["company"] = company or None
    out["title"] = title or None
    out["location"] = location or None
    out["jd_text"] = jd_text or None

    if out.get("eval_score") is not None:
        out["eval_score"] = float(out["eval_score"])
    if eval_data.get("score") is not None and out.get("eval_score") is None:
        out["eval_score"] = float(eval_data["score"])
    if out.get("eval_legitimacy"):
        out["legitimacy"] = out["eval_legitimacy"]
    elif eval_data.get("legitimacy"):
        out["legitimacy"] = eval_data["legitimacy"]

    if blocks:
        try:
            from writing.sanitize import sanitize_blocks

            blocks = sanitize_blocks(blocks, mode="prose")
        except Exception:
            pass
        out["eval_blocks"] = blocks
    out["eval_template_only"] = bool(
        eval_data.get("template_only")
        or eval_data.get("eval_mode") == "template"
        or (blocks and is_boilerplate_text(str(blocks.get("A", ""))) and len(blocks) <= 3)
    )

    return out


def _extract_title_from_jd(jd: str) -> str:
    if not jd:
        return ""
    for pat in (
        r"(?im)^(?:job title|position|role)\s*[:\-]\s*(.+)$",
        r"(?im)^#\s+(.+)$",
        r"(?i)\b((?:senior|staff|principal|lead|head of|director of)[^\n.]{4,80})",
    ):
        m = re.search(pat, jd[:2000])
        if m:
            candidate = m.group(1).strip()
            if not is_boilerplate_text(candidate) and len(candidate) > 4:
                return candidate[:120]
    first = jd.strip().split("\n")[0].strip()
    if len(first) > 8 and len(first) < 100 and not is_boilerplate_text(first):
        return first
    return ""


def resolve_job_from_url(url: str) -> dict[str, Any] | None:
    """Fetch job metadata from ATS URL (network)."""
    if not url:
        return None
    try:
        from scrapers.ats_url_resolver import resolve_job_url

        resolved = resolve_job_url(url)
        if resolved and resolved.get("company"):
            resolved["company"] = prettify_company(str(resolved["company"]))
        return resolved
    except Exception:
        return None


def persist_resolved_job(job_id: str, resolved: dict[str, Any]) -> None:
    """Write resolved ATS fields back to SQLite."""
    from store import db as store

    company = prettify_company(str(resolved.get("company") or ""))
    title = str(resolved.get("title") or "").strip()
    location = str(resolved.get("location") or "").strip()
    jd = html_to_plain(resolved.get("jd_snippet") or resolved.get("description") or "")

    with store.db() as conn:
        row = conn.execute(
            "SELECT company, title, location, jd_text FROM jobs WHERE id = ?", (job_id,)
        ).fetchone()
        if not row:
            return
        conn.execute(
            """
            UPDATE jobs SET
                company = CASE WHEN ? = '' OR company IS NULL OR LOWER(TRIM(company)) IN ('unknown','import','') THEN ? ELSE company END,
                title = CASE WHEN ? = '' OR title IS NULL OR LOWER(TRIM(title)) IN ('unknown','untitled','') THEN ? ELSE title END,
                location = CASE WHEN ? = '' OR location IS NULL OR TRIM(location) = '' THEN ? ELSE location END,
                jd_text = CASE WHEN ? = '' OR jd_text IS NULL OR TRIM(jd_text) = '' THEN ? ELSE jd_text END,
                updated_at = datetime('now')
            WHERE id = ?
            """,
            (company, company, title, title, location, location, jd, jd, job_id),
        )


def backfill_all_jobs(conn, *, max_jobs: int = 50) -> int:
    """Resolve ATS metadata for every job missing company/title."""
    rows = conn.execute("SELECT * FROM jobs ORDER BY updated_at DESC").fetchall()
    return backfill_missing_metadata(conn, [dict(r) for r in rows], max_jobs=max_jobs)


def backfill_missing_metadata(
    conn,
    rows: list[dict[str, Any]],
    *,
    max_jobs: int = 10,
) -> int:
    """Resolve ATS URLs for jobs missing title/company (network, capped)."""
    from scrapers.ats_url_resolver import can_resolve_job_url

    done = 0
    for row in rows:
        if done >= max_jobs:
            break
        job_id = row.get("id")
        url = row.get("url") or ""
        if not job_id or not url:
            continue
        needs = (
            is_placeholder(row.get("title"))
            or is_placeholder(row.get("company"))
            or is_boilerplate_text(str(row.get("jd_text") or ""))
        )
        if not needs or not can_resolve_job_url(url):
            continue
        resolved = resolve_job_from_url(url)
        if resolved:
            persist_resolved_job(job_id, resolved)
            done += 1
    return done
