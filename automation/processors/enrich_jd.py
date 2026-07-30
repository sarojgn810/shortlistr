"""Fill empty jd_text by fetching the posting page and compressing it.

Used after discovery and before eval so LinkedIn guest / search cards are not
scored on title alone. Never submits applications.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from scrapers.browser_fetch import fetch_page
from scrapers.html_text import html_to_markdown, html_to_plain

logger = logging.getLogger(__name__)

MIN_JD_CHARS = 200
DEFAULT_LIMIT = 20
_THIN_SOURCES = frozenset({
    "LinkedIn",
    "SearchDiscovery",
    "Careers",
    "Naukri",
})


def _is_thin(jd: str | None) -> bool:
    text = (jd or "").strip()
    return len(text) < MIN_JD_CHARS


def enrich_job_page(job: dict[str, Any], *, allow_browser: bool = True) -> dict[str, Any]:
    """Fetch + compress one job URL into jd_text fields. Returns update dict."""
    url = str(job.get("url") or "").strip()
    out: dict[str, Any] = {"url": url, "ok": False, "error": "", "jd_text": ""}
    if not url:
        out["error"] = "missing url"
        return out

    page = fetch_page(url, allow_browser=allow_browser)
    if page.error and not page.html:
        out["error"] = page.error
        return out

    md = html_to_markdown(page.html, max_len=12000, base_url=page.final_url or url)
    plain = html_to_plain(md, max_len=8000) if md else ""
    if len(plain) < MIN_JD_CHARS:
        out["error"] = page.error or "page text too short"
        out["jd_text"] = plain
        return out

    out["ok"] = True
    out["jd_text"] = plain
    out["via"] = page.via
    # Best-effort title from first markdown heading if the card title is empty.
    if not str(job.get("title") or "").strip():
        m = re.search(r"^#\s+(.+)$", md, re.M)
        if m:
            out["title"] = m.group(1).strip()[:160]
    return out


def enrich_stub_jobs(
    *,
    limit: int = DEFAULT_LIMIT,
    allow_browser: bool = True,
    sources: set[str] | None = None,
) -> dict[str, int]:
    """Persist JD text for thin rows already in SQLite."""
    from store import db as store

    store.init_db()
    wanted = sources or set(_THIN_SOURCES)
    updated = 0
    failed = 0
    scanned = 0

    with store.db() as conn:
        rows = conn.execute(
            """
            SELECT id, url, title, source, jd_text
            FROM jobs
            WHERE archived_at IS NULL
              AND source != 'eval'
              AND (jd_text IS NULL OR length(trim(jd_text)) < ?)
            ORDER BY discovered_at DESC, updated_at DESC
            LIMIT ?
            """,
            (MIN_JD_CHARS, max(limit * 3, limit)),
        ).fetchall()

        for row in rows:
            if scanned >= limit:
                break
            source = str(row["source"] or "")
            if wanted and source not in wanted:
                continue
            scanned += 1
            result = enrich_job_page(dict(row), allow_browser=allow_browser)
            if not result.get("ok"):
                failed += 1
                logger.debug(
                    "JD enrich %s failed: %s", row["id"], result.get("error") or ""
                )
                continue
            jd = str(result["jd_text"])
            title = str(result.get("title") or "").strip()
            conn.execute(
                """
                UPDATE jobs SET
                    jd_text = CASE
                        WHEN jd_text IS NULL OR length(trim(jd_text)) < ? THEN ?
                        ELSE jd_text
                    END,
                    title = CASE
                        WHEN ? != '' AND (title IS NULL OR trim(title) = '') THEN ?
                        ELSE title
                    END,
                    updated_at = datetime('now')
                WHERE id = ?
                """,
                (MIN_JD_CHARS, jd, title, title, row["id"]),
            )
            updated += 1

    logger.info(
        "JD enrich: scanned=%s updated=%s failed=%s", scanned, updated, failed
    )
    return {"scanned": scanned, "updated": updated, "failed": failed}
