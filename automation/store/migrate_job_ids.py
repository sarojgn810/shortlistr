"""One-time migration: rewrite non-canonical job ids to the URL hash.

Older rows (and any discovered before the JobRecord fix) could have a
source-provided id — a URL, an RSS guid, or a numeric source id — stored as the
primary key. Those fail the API's 16-hex `validate_job_id`, making the job
non-actionable. This rewrites every such id to `job_id_from_url(url)` across all
tables that reference it, deduping when the canonical id already exists.
"""

from __future__ import annotations

import re
import sqlite3

from models.job import job_id_from_url
from store import db as store

_HEX16 = re.compile(r"^[a-f0-9]{16}$")
_REFERENCING = ("pipeline", "applications", "eval_results", "application_receipts")


def migrate_job_ids() -> dict[str, int]:
    """Returns counts: {scanned, rewritten, deduped, skipped_no_url}."""
    store.init_db()
    stats = {"scanned": 0, "rewritten": 0, "deduped": 0, "skipped_no_url": 0}

    # Rewriting a primary key while children reference it trips the FK constraint
    # mid-transaction. Use a dedicated connection with enforcement off; we keep
    # parent + child rows consistent ourselves, then re-verify integrity below.
    conn = sqlite3.connect(store.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = OFF")
        rows = conn.execute("SELECT id, url FROM jobs").fetchall()
        existing = {str(r["id"]) for r in rows}

        for row in rows:
            old = str(row["id"])
            stats["scanned"] += 1
            if _HEX16.match(old):
                continue
            url = (row["url"] or "").strip()
            if not url:
                stats["skipped_no_url"] += 1
                continue
            new = job_id_from_url(url)
            if not new or new == old:
                continue

            if new in existing:
                # Canonical row already exists — drop the broken duplicate and
                # its references rather than violate the primary key.
                for tbl in _REFERENCING:
                    conn.execute(f"DELETE FROM {tbl} WHERE job_id = ?", (old,))
                conn.execute("DELETE FROM jobs WHERE id = ?", (old,))
                stats["deduped"] += 1
            else:
                conn.execute("UPDATE jobs SET id = ? WHERE id = ?", (new, old))
                for tbl in _REFERENCING:
                    conn.execute(
                        f"UPDATE {tbl} SET job_id = ? WHERE job_id = ?", (new, old)
                    )
                existing.discard(old)
                existing.add(new)
                stats["rewritten"] += 1

        # Catch any FK breakage we may have introduced before committing.
        violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            conn.rollback()
            raise RuntimeError(f"migration aborted: {len(violations)} FK violations")
        conn.commit()
    finally:
        conn.close()

    store.audit("migrate_job_ids", "system", "default", stats)
    return stats


def main() -> int:
    stats = migrate_job_ids()
    print(
        f"job-id migration: scanned={stats['scanned']} "
        f"rewritten={stats['rewritten']} deduped={stats['deduped']} "
        f"skipped_no_url={stats['skipped_no_url']}"
    )
    return 0
