"""Job liveness sweep: archive listings that have gone dead, purge old archives.

Design rules (from the job-bridge plan):
- Jobs are ARCHIVED, never deleted on the spot. `archived_at` hides them from
  candidate matching immediately and is reversible.
- Two strikes before archiving. One dead verdict is usually a timeout, a rate
  limit, or a WAF — not a closed req. A live verdict resets the count.
- HTTP first (fast, ~1s), Playwright only for `uncertain` verdicts, because a
  browser check costs ~17s and the corpus is thousands of rows.
- Purge only after 30 days AND only when nothing references the job.

The verdict logic itself is `tracker_tools.liveness.classify_liveness`, shared
with the interactive checker so both agree on what "dead" means.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

import requests

from store import db as store
from tracker_tools.liveness import classify_liveness

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
ARCHIVE_AFTER_STRIKES = 2
DEFAULT_PURGE_DAYS = 30

_ANCHOR_RE = re.compile(
    r"<(?:a|button)\b[^>]*>(.*?)</(?:a|button)>", re.I | re.S
)


def _now() -> str:
    """SQLite's own datetime() format, NOT isoformat().

    These columns are compared against datetime('now', ...) in SQL. An ISO string
    ('2026-07-25T09:50:00+00:00') sorts above SQLite's ('2026-07-25 09:50:00')
    because 'T' > ' ', so a mixed-format comparison silently never matches and the
    recheck window would never open.
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _apply_controls_from_html(html: str) -> list[str]:
    """Crude anchor/button label extraction so classify_liveness can look for an
    apply control without a browser. Deliberately permissive — a false 'active'
    only delays an archive by one sweep, while a false 'dead' hides a real job."""
    from scrapers.html_text import html_to_plain

    labels = []
    for m in _ANCHOR_RE.finditer(html or ""):
        label = html_to_plain(m.group(1), max_len=120).strip()
        if label:
            labels.append(label)
        if len(labels) > 400:
            break
    return labels


def check_url_http(url: str, *, timeout: int = 12) -> dict[str, str]:
    """Fast HTTP liveness verdict: live | dead | uncertain."""
    from scrapers.html_text import html_to_plain

    try:
        resp = requests.get(
            url, timeout=timeout, headers={"User-Agent": USER_AGENT}, allow_redirects=True
        )
    except requests.RequestException as e:
        # Network failure says nothing about the posting — never counts as dead.
        return {"result": "uncertain", "reason": f"request failed: {type(e).__name__}"}

    if resp.status_code in (403, 429) or resp.status_code >= 500:
        return {"result": "uncertain", "reason": f"HTTP {resp.status_code} (blocked/transient)"}

    body = html_to_plain(resp.text or "", max_len=20000)
    verdict = classify_liveness(
        status=resp.status_code,
        final_url=str(resp.url),
        body_text=body,
        apply_controls=_apply_controls_from_html(resp.text or ""),
    )
    # classify_liveness speaks active/expired/uncertain; this module speaks
    # live/dead/uncertain so the DB column reads plainly.
    mapping = {"active": "live", "expired": "dead", "uncertain": "uncertain"}
    return {"result": mapping.get(verdict["result"], "uncertain"), "reason": verdict["reason"]}


def _select_due(conn, *, limit: int, recheck_after_hours: int) -> list:
    # recheck_after_hours <= 0 means "check everything now" (used by tests and by
    # an operator forcing a full re-sweep); otherwise only rows past the window.
    window = ""
    params: list = []
    if recheck_after_hours > 0:
        window = "AND (last_checked_at IS NULL OR last_checked_at < datetime('now', ?))"
        params.append(f"-{int(recheck_after_hours)} hours")
    params.append(limit)
    return conn.execute(
        f"""
        SELECT id, url, dead_strikes FROM jobs
        WHERE archived_at IS NULL
          AND url IS NOT NULL AND url != ''
          {window}
        ORDER BY last_checked_at IS NOT NULL, last_checked_at ASC
        LIMIT ?
        """,
        params,
    ).fetchall()


def sweep(
    *,
    limit: int = 300,
    recheck_after_hours: int = 72,
    dry_run: bool = False,
    use_browser: bool = False,
) -> dict:
    """Check the least-recently-checked live jobs; archive on the 2nd dead strike."""
    store.init_db()
    with store.db() as conn:
        due = _select_due(conn, limit=limit, recheck_after_hours=recheck_after_hours)

    checked = live = dead = uncertain = archived = 0
    for row in due:
        verdict = check_url_http(row["url"])
        result = verdict["result"]
        if result == "uncertain" and use_browser:
            result = _browser_recheck(row["url"], result)
        checked += 1

        if result == "live":
            live += 1
            strikes = 0
        elif result == "dead":
            dead += 1
            strikes = int(row["dead_strikes"] or 0) + 1
        else:
            uncertain += 1
            strikes = int(row["dead_strikes"] or 0)  # unchanged; never punish uncertainty

        will_archive = result == "dead" and strikes >= ARCHIVE_AFTER_STRIKES
        if dry_run:
            if will_archive:
                archived += 1
            continue

        with store.db() as conn:
            conn.execute(
                """
                UPDATE jobs SET liveness = ?, last_checked_at = ?, dead_strikes = ?,
                    archived_at = CASE WHEN ? THEN ? ELSE archived_at END
                WHERE id = ?
                """,
                (result, _now(), strikes, 1 if will_archive else 0,
                 _now() if will_archive else None, row["id"]),
            )
        if will_archive:
            archived += 1
            store.audit("job_archived", "job", row["id"],
                        {"reason": verdict["reason"], "strikes": strikes})

    return {"checked": checked, "live": live, "dead": dead, "uncertain": uncertain,
            "archived": archived, "dry_run": dry_run}


def _browser_recheck(url: str, fallback: str) -> str:
    """Playwright second opinion for uncertain verdicts (slow; opt-in)."""
    try:
        from playwright.sync_api import sync_playwright

        from tracker_tools.liveness import check_url_with_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                res = check_url_with_playwright(page, url)
            finally:
                browser.close()
        return {"active": "live", "expired": "dead"}.get(res["result"], "uncertain")
    except Exception as e:
        logger.warning("browser recheck failed for %s: %s", url, e)
        return fallback


def purge_archived(*, older_than_days: int = DEFAULT_PURGE_DAYS, dry_run: bool = False) -> dict:
    """Hard-delete long-archived jobs that nothing references.

    Referenced = has a referral, an application, or a pipeline row that moved past
    'pending'. Those are history; losing them would corrupt the conversion metrics.
    """
    store.init_db()
    cutoff = f"-{int(older_than_days)} days"
    with store.db() as conn:
        rows = conn.execute(
            """
            SELECT j.id FROM jobs j
            WHERE j.archived_at IS NOT NULL
              AND j.archived_at < datetime('now', ?)
              AND NOT EXISTS (SELECT 1 FROM referrals r WHERE r.job_id = j.id)
              AND NOT EXISTS (SELECT 1 FROM applications a WHERE a.job_id = j.id)
              AND NOT EXISTS (SELECT 1 FROM pipeline p
                              WHERE p.job_id = j.id AND p.status != 'pending')
            """,
            (cutoff,),
        ).fetchall()
        ids = [r["id"] for r in rows]
        if not dry_run and ids:
            chunk = [(i,) for i in ids]
            # pipeline.job_id REFERENCES jobs(id) with foreign_keys ON — clear the
            # child rows (all still 'pending' by the guard above) before the parent.
            conn.executemany("DELETE FROM pipeline WHERE job_id = ?", chunk)
            conn.executemany("DELETE FROM eval_results WHERE job_id = ?", chunk)
            conn.executemany("DELETE FROM jobs WHERE id = ?", chunk)

    if ids and not dry_run:
        store.audit("jobs_purged", "job", "", {"count": len(ids)})
    return {"purged": len(ids), "dry_run": dry_run}
