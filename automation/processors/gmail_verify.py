"""Confirm Gmail alert rows against a live posting before Discover publish.

Unverified Gmail stubs stay in the DB (tagged) but are excluded from the default
relevant inbox until a URL fetch returns a real JD (or ATS resolve succeeds).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from processors.job_display import apply_structure_to_job, structure_from_blob

logger = logging.getLogger(__name__)

MIN_JD_CHARS = 200
VERIFIED = "confirmed"
UNVERIFIED = "unverified"


def _meta(job: dict[str, Any]) -> dict[str, Any]:
    raw = job.get("metadata_json") or job.get("metadata") or {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = {}
    return dict(raw) if isinstance(raw, dict) else {}


# Sources whose rows are links mined out of an email and therefore have to be
# confirmed against a live posting before Discover shows them. Keyed on "this
# came from a mailbox", not on which provider hosts it — an Outlook alert is
# exactly as unverified as a Gmail one, and gating on "gmail" alone let every
# other provider's rows through unchecked.
EMAIL_SOURCES = {"gmail", "email", "imap", "outlook", "mailbox"}


def is_email_source(source: str | None) -> bool:
    return (source or "").strip().lower() in EMAIL_SOURCES


def is_gmail_source(source: str | None) -> bool:
    """Back-compat alias. Prefer is_email_source — verification is not Gmail's."""
    return is_email_source(source)


def structure_job_record_fields(job: Any) -> Any:
    """Apply blob structuring onto a JobRecord (mutates and returns it)."""
    from models.job import JobRecord

    if not isinstance(job, JobRecord):
        return job
    structured = structure_from_blob(
        title=job.title or "",
        company=job.company or "",
        location=job.location or "",
        experience=str((job.metadata or {}).get("experience") or ""),
    )
    if structured["title"]:
        job.title = structured["title"]
    if structured["company"] and (
        not job.company or job.company.strip().lower() in {"unknown", "untitled"}
    ):
        job.company = structured["company"]
    if structured["location"] and not (job.location or "").strip():
        job.location = structured["location"]
    if structured["experience"]:
        job.metadata = dict(job.metadata or {})
        job.metadata.setdefault("experience", structured["experience"])
    return job


def verify_gmail_job(job: dict[str, Any], *, allow_browser: bool = False) -> dict[str, Any]:
    """Try to confirm a live posting; return update fields + verification status.

    Always applies structure_from_blob. Sets metadata.verification to confirmed
    when a substantial JD is fetched; otherwise unverified.
    """
    out = apply_structure_to_job(job)
    meta = _meta(out)
    url = str(out.get("url") or "").strip()
    source = str(out.get("source") or "")

    if not is_email_source(source):
        meta.setdefault("verification", VERIFIED)
        out["metadata"] = meta
        return out

    # Already confirmed with a real JD — keep.
    jd = str(out.get("jd_text") or "").strip()
    if len(jd) >= MIN_JD_CHARS and meta.get("verification") == VERIFIED:
        out["metadata"] = meta
        return out

    confirmed = False
    note = ""

    if url:
        try:
            from scrapers.ats_url_resolver import resolve_job_url

            resolved = resolve_job_url(url)
            if resolved:
                for key in ("title", "company", "location", "jd_text", "salary"):
                    val = (resolved.get(key) or "").strip()
                    if val and (
                        not out.get(key)
                        or key == "jd_text"
                        or str(out.get(key)).lower() in {"unknown", "untitled", "email alert"}
                    ):
                        out[key] = val
                if len(str(out.get("jd_text") or "")) >= MIN_JD_CHARS:
                    confirmed = True
                    note = "ats_resolve"
        except Exception as exc:
            logger.debug("gmail verify resolve failed: %s", exc)

    if not confirmed and url:
        try:
            from processors.enrich_jd import enrich_job_page

            page = enrich_job_page(out, allow_browser=allow_browser)
            if page.get("ok") and len(str(page.get("jd_text") or "")) >= MIN_JD_CHARS:
                out["jd_text"] = page["jd_text"]
                if page.get("title") and (
                    not out.get("title") or len(str(out.get("title"))) > 80
                ):
                    out["title"] = page["title"]
                confirmed = True
                note = page.get("via") or "page_fetch"
            elif page.get("error"):
                note = str(page.get("error"))[:180]
        except Exception as exc:
            note = str(exc)[:180]
            logger.debug("gmail verify page fetch failed: %s", exc)

    # Keyword hint for a later search pass (stored; not auto-blasting Apify here).
    if not confirmed:
        keywords = " ".join(
            p
            for p in (
                str(out.get("title") or "").strip(),
                str(out.get("company") or "").strip(),
                str(out.get("location") or "").strip(),
            )
            if p
        ).strip()
        if keywords:
            meta["verify_keywords"] = keywords[:200]

    meta["verification"] = VERIFIED if confirmed else UNVERIFIED
    if note:
        meta["verify_note"] = note[:240]
    if out.get("experience"):
        meta["experience"] = out["experience"]
    out["metadata"] = meta
    # Re-structure after resolve may have filled company/title
    out = apply_structure_to_job(out)
    out["metadata"] = meta
    return out


def prepare_gmail_records(jobs: list) -> list:
    """Structure + verify Gmail JobRecords before persist."""
    from models.job import JobRecord

    prepared: list = []
    for job in jobs:
        if not isinstance(job, JobRecord):
            prepared.append(job)
            continue
        structure_job_record_fields(job)
        as_dict = {
            "url": job.url,
            "source": job.source,
            "company": job.company,
            "title": job.title,
            "location": job.location,
            "jd_text": job.jd_text,
            "salary": job.salary,
            "metadata": dict(job.metadata or {}),
            "experience": (job.metadata or {}).get("experience") or "",
        }
        verified = verify_gmail_job(as_dict, allow_browser=False)
        job.title = str(verified.get("title") or job.title)
        job.company = str(verified.get("company") or job.company)
        job.location = str(verified.get("location") or job.location)
        job.jd_text = str(verified.get("jd_text") or job.jd_text)
        job.salary = str(verified.get("salary") or job.salary)
        job.metadata = dict(verified.get("metadata") or job.metadata or {})
        if verified.get("experience"):
            job.metadata["experience"] = verified["experience"]
        prepared.append(job)
    return prepared


def verify_pending_gmail_stubs(*, limit: int = 25, allow_browser: bool = False) -> dict[str, int]:
    """Re-check unverified Gmail rows; promote when a live JD appears."""
    from store import db as store

    store.init_db()
    confirmed = 0
    checked = 0
    with store.db() as conn:
        rows = conn.execute(
            """
            SELECT id, url, source, company, title, location, jd_text, salary, metadata_json
            FROM jobs
            WHERE archived_at IS NULL
              AND LOWER(COALESCE(source, '')) = 'gmail'
              AND COALESCE(json_extract(metadata_json, '$.verification'), 'unverified')
                  = 'unverified'
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    for row in rows:
        checked += 1
        job = dict(row)
        result = verify_gmail_job(job, allow_browser=allow_browser)
        meta = result.get("metadata") or {}
        with store.db() as conn:
            conn.execute(
                """
                UPDATE jobs SET
                  title = ?, company = ?, location = ?, jd_text = ?, salary = ?,
                  metadata_json = ?, updated_at = datetime('now')
                WHERE id = ?
                """,
                (
                    result.get("title") or job.get("title"),
                    result.get("company") or job.get("company"),
                    result.get("location") or job.get("location"),
                    result.get("jd_text") or job.get("jd_text") or "",
                    result.get("salary") or job.get("salary") or "",
                    json.dumps(meta),
                    job["id"],
                ),
            )
        if meta.get("verification") == VERIFIED:
            confirmed += 1

    return {"checked": checked, "confirmed": confirmed}
