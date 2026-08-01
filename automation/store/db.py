"""SQLite job store — system of record for Phase 1."""

from __future__ import annotations

import contextvars
import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

from config import DATA_DIR
from models.job import JobRecord, job_id_from_url

DB_PATH = os.path.join(DATA_DIR, "shortlistr.db")
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")
MIGRATIONS_DIR = os.path.join(os.path.dirname(__file__), "migrations")

# ── two databases, one schema ────────────────────────────────────────────────
#
# The PERSONAL database (data/shortlistr.db) is the owner's own job search: their
# discovery inbox, evaluations, applications. Anyone who clones the repo gets
# only this one.
#
# The PLATFORM database (data/platform.db) belongs to Layer 3 — candidate
# sessions, resumes, referrals, referrers. Other people's data must never sit in
# the owner's personal file, and the owner's job hunt must never leak into the
# platform. Jobs cross the boundary only through an explicit `publish`.
#
# Both use the identical schema + migration ladder, so a row means the same
# thing on either side and there is no second schema to maintain.

_active_db: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "autojob_active_db", default=None
)


def platform_db_path() -> str:
    """Where Layer 3 keeps its data.

    Resolved at call time so DATA_DIR monkeypatching (tests) still isolates it.
    SHORTLISTR_PLATFORM_DB lets the platform repo own its own data directory rather
    than borrowing the engine's.
    """
    override = os.environ.get("SHORTLISTR_PLATFORM_DB", "").strip()
    return override or os.path.join(DATA_DIR, "platform.db")


def active_db_path() -> str:
    return _active_db.get() or DB_PATH


@contextmanager
def using_platform_db():
    """Run a block against the Layer 3 database.

    Layer 3 entry points enter this, so Layer 1 helpers they call (upsert_jobs,
    audit, …) transparently write to the platform file instead of the owner's.
    Re-entrant: nesting is a no-op.
    """
    path = platform_db_path()
    if _active_db.get() == path:
        yield
        return
    token = _active_db.set(path)
    try:
        yield
    finally:
        _active_db.reset(token)


def is_platform_scope() -> bool:
    return _active_db.get() == platform_db_path()


def _schema_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
    return int(row["version"]) if row else 0


def _add_column_if_missing(conn: sqlite3.Connection, table: str, column: str, decl: str) -> None:
    """SQLite has no ADD COLUMN IF NOT EXISTS; a migration that half-applied must
    still be safe to re-run."""
    cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


def _run_migrations(conn: sqlite3.Connection) -> None:
    version = _schema_version(conn)
    if version < 2:
        v2_path = os.path.join(MIGRATIONS_DIR, "v2.sql")
        if os.path.exists(v2_path):
            conn.executescript(open(v2_path, encoding="utf-8").read())
        if version == 0:
            conn.execute("INSERT INTO schema_version (version) VALUES (2)")
        else:
            conn.execute("UPDATE schema_version SET version = 2")
        version = 2
    if version < 3:
        v3_path = os.path.join(MIGRATIONS_DIR, "v3.sql")
        if os.path.exists(v3_path):
            conn.executescript(open(v3_path, encoding="utf-8").read())
        conn.execute("UPDATE schema_version SET version = 3")
        version = 3
    if version < 4:
        v4_path = os.path.join(MIGRATIONS_DIR, "v4.sql")
        if os.path.exists(v4_path):
            conn.executescript(open(v4_path, encoding="utf-8").read())
        conn.execute("UPDATE schema_version SET version = 4")
        version = 4
    if version < 5:
        v5_path = os.path.join(MIGRATIONS_DIR, "v5.sql")
        if os.path.exists(v5_path):
            conn.executescript(open(v5_path, encoding="utf-8").read())
        conn.execute("UPDATE schema_version SET version = 5")
        version = 5
    if version < 6:
        v6_path = os.path.join(MIGRATIONS_DIR, "v6.sql")
        if os.path.exists(v6_path):
            conn.executescript(open(v6_path, encoding="utf-8").read())
        conn.execute("UPDATE schema_version SET version = 6")
        version = 6
    if version < 7:
        # Columns first: v7.sql's indexes reference them, and ADD COLUMN is not
        # idempotent in SQLite, so it is guarded rather than scripted.
        _add_column_if_missing(conn, "jobs", "archived_at", "TEXT")
        _add_column_if_missing(conn, "jobs", "last_checked_at", "TEXT")
        _add_column_if_missing(conn, "jobs", "liveness", "TEXT")
        _add_column_if_missing(conn, "jobs", "dead_strikes", "INTEGER NOT NULL DEFAULT 0")
        _add_column_if_missing(conn, "referrals", "job_id", "TEXT")
        _add_column_if_missing(conn, "referrals", "company", "TEXT NOT NULL DEFAULT ''")
        v7_path = os.path.join(MIGRATIONS_DIR, "v7.sql")
        if os.path.exists(v7_path):
            conn.executescript(open(v7_path, encoding="utf-8").read())
        conn.execute("UPDATE schema_version SET version = 7")
        version = 7
    if version < 8:
        # NULL review_status = scraped by us, auto-trusted. User-submitted rows
        # are 'pending' until an admin approves them.
        _add_column_if_missing(conn, "jobs", "review_status", "TEXT")
        _add_column_if_missing(conn, "jobs", "referrer_phone", "TEXT")
        _add_column_if_missing(conn, "jobs", "submitted_by", "TEXT")
        v8_path = os.path.join(MIGRATIONS_DIR, "v8.sql")
        if os.path.exists(v8_path):
            conn.executescript(open(v8_path, encoding="utf-8").read())
        conn.execute("UPDATE schema_version SET version = 8")
        version = 8
    if version < 9:
        # Ownership for generated files. Only the platform database ever gets
        # rows here; the personal instance generates nothing it needs to serve.
        v9_path = os.path.join(MIGRATIONS_DIR, "v9.sql")
        if os.path.exists(v9_path):
            conn.executescript(open(v9_path, encoding="utf-8").read())
        conn.execute("UPDATE schema_version SET version = 9")
        version = 9
    if version < 10:
        # Proof-of-possession for a phone number. Platform database only.
        v10_path = os.path.join(MIGRATIONS_DIR, "v10.sql")
        if os.path.exists(v10_path):
            conn.executescript(open(v10_path, encoding="utf-8").read())
        conn.execute("UPDATE schema_version SET version = 10")
        version = 10
    if version < 11:
        # A referral belongs to somebody. Platform database only.
        # Columns first: v11.sql's unique index reads `status` and the inbox
        # index reads `referrer_id`, and ADD COLUMN is not idempotent.
        _add_column_if_missing(conn, "referrals", "referrer_id", "INTEGER")
        _add_column_if_missing(conn, "referrals", "claimed_at", "TEXT")
        v11_path = os.path.join(MIGRATIONS_DIR, "v11.sql")
        if os.path.exists(v11_path):
            conn.executescript(open(v11_path, encoding="utf-8").read())
        conn.execute("UPDATE schema_version SET version = 11")
        version = 11
    if version < 12:
        # An outbox, plus proof a referrer works where they say. Platform only.
        _add_column_if_missing(conn, "referrers", "work_email", "TEXT")
        _add_column_if_missing(conn, "referrers", "verify_code", "TEXT")
        _add_column_if_missing(conn, "referrers", "verify_sent_at", "TEXT")
        _add_column_if_missing(conn, "referrers", "verify_attempts",
                               "INTEGER NOT NULL DEFAULT 0")
        v12_path = os.path.join(MIGRATIONS_DIR, "v12.sql")
        if os.path.exists(v12_path):
            conn.executescript(open(v12_path, encoding="utf-8").read())
        conn.execute("UPDATE schema_version SET version = 12")
        version = 12
    if version < 13:
        # A role listed without naming the employer. Presentation only —
        # `company` keeps the real name so the confidentiality gate, which
        # compares it against the candidate's own employer, keeps working.
        _add_column_if_missing(conn, "jobs", "company_confidential",
                               "INTEGER NOT NULL DEFAULT 0")
        _add_column_if_missing(conn, "jobs", "company_hint", "TEXT")
        v13_path = os.path.join(MIGRATIONS_DIR, "v13.sql")
        if os.path.exists(v13_path):
            conn.executescript(open(v13_path, encoding="utf-8").read())
        conn.execute("UPDATE schema_version SET version = 13")
        version = 13
    if version < 14:
        # A Telegram chat we can reach a person through. Platform only.
        v14_path = os.path.join(MIGRATIONS_DIR, "v14.sql")
        if os.path.exists(v14_path):
            conn.executescript(open(v14_path, encoding="utf-8").read())
        conn.execute("UPDATE schema_version SET version = 14")
        version = 14
    if version < 15:
        # When a task was claimed, so a worker that died mid-task can be told
        # apart from one that is still working. Without it a killed process left
        # its row 'running' forever, and `_claim_pending` cancels every new
        # discover while one is running — the Scan button spun indefinitely and
        # no scan could ever start again.
        _add_column_if_missing(conn, "worker_queue", "started_at", "TEXT")
        conn.execute("UPDATE schema_version SET version = 15")
        version = 15
    if version < 16:
        # Contact-resolution: company domain/MX, people, email candidates, evidence.
        v16_path = os.path.join(MIGRATIONS_DIR, "v16.sql")
        if os.path.exists(v16_path):
            conn.executescript(open(v16_path, encoding="utf-8").read())
        conn.execute("UPDATE schema_version SET version = 16")


def _connect() -> sqlite3.Connection:
    os.makedirs(DATA_DIR, exist_ok=True)
    # active_db_path(), not DB_PATH: inside using_platform_db() every connection
    # — including ones opened by Layer 1 helpers — goes to the platform file.
    conn = sqlite3.connect(active_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(open(SCHEMA_PATH, encoding="utf-8").read())
        if _schema_version(conn) == 0:
            conn.execute("INSERT INTO schema_version (version) VALUES (1)")
        _run_migrations(conn)
        conn.execute(
            "INSERT OR IGNORE INTO tenants (id, name) VALUES ('default', 'default')"
        )
        conn.commit()


@contextmanager
def db():
    init_db()
    conn = _connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


@contextmanager
def platform_db():
    """A connection to the Layer 3 database, for admin tooling and tests.

    Application code should not need this: Layer 3 entry points are wrapped in
    @platform_scoped, so `db()` already resolves to the platform file inside them.
    """
    with using_platform_db():
        with db() as conn:
            yield conn


def _job_params(job: JobRecord) -> tuple:
    return (
        job.job_id or job_id_from_url(job.url),
        job.url, job.source, job.company, job.title, job.location,
        job.jd_text, job.salary, job.department, job.company_email,
        job.status, job.email_sent, job.notes, job.fit_score,
        job.fit_reason, job.discovered_at, json.dumps(job.metadata),
    )


# The v7 lifecycle columns (archived_at, last_checked_at, liveness, dead_strikes)
# are deliberately absent from both the INSERT list and the DO UPDATE SET clause:
# a re-scrape must never resurrect an archived job or wipe its check history.
_UPSERT_JOB_SQL = """
            INSERT INTO jobs (
                id, url, source, company, title, location, jd_text, salary,
                department, company_email, status, email_sent, notes,
                fit_score, fit_reason, discovered_at, metadata_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(id) DO UPDATE SET
                company=CASE
                    WHEN excluded.company IS NOT NULL AND TRIM(excluded.company) != ''
                         AND LOWER(TRIM(excluded.company)) NOT IN ('unknown','')
                    THEN excluded.company
                    ELSE jobs.company
                END,
                title=CASE
                    WHEN excluded.title IS NOT NULL AND TRIM(excluded.title) != ''
                         AND LOWER(TRIM(excluded.title)) NOT IN ('unknown','untitled','')
                    THEN excluded.title
                    ELSE jobs.title
                END,
                location=CASE
                    WHEN excluded.location IS NOT NULL AND TRIM(excluded.location) != ''
                    THEN excluded.location
                    ELSE jobs.location
                END,
                salary=CASE
                    WHEN excluded.salary IS NOT NULL AND TRIM(excluded.salary) != ''
                    THEN excluded.salary
                    ELSE jobs.salary
                END,
                jd_text=CASE
                    WHEN excluded.jd_text IS NOT NULL AND TRIM(excluded.jd_text) != ''
                    THEN excluded.jd_text
                    ELSE jobs.jd_text
                END,
                metadata_json=CASE
                    WHEN excluded.metadata_json IS NOT NULL AND TRIM(excluded.metadata_json) NOT IN ('', '{}')
                    THEN excluded.metadata_json
                    ELSE jobs.metadata_json
                END,
                -- 'eval' is the artifact marker for a pasted-URL evaluation (see
                -- queries.NO_EVAL_ARTIFACTS). Evaluating a discovered job must not
                -- rewrite its provenance, or that filter hides the job afterwards.
                source=CASE
                    WHEN excluded.source IS NULL OR TRIM(excluded.source) = ''
                    THEN jobs.source
                    WHEN excluded.source = 'eval' AND jobs.source IS NOT NULL
                         AND TRIM(jobs.source) NOT IN ('', 'eval')
                    THEN jobs.source
                    ELSE excluded.source
                END,
                -- A score of 0 means "not scored by this writer", not "scored zero".
                fit_score=CASE
                    WHEN COALESCE(excluded.fit_score, 0) != 0
                    THEN excluded.fit_score
                    ELSE jobs.fit_score
                END,
                fit_reason=CASE
                    WHEN COALESCE(excluded.fit_score, 0) != 0
                    THEN excluded.fit_reason
                    ELSE jobs.fit_reason
                END,
                status=excluded.status,
                updated_at=datetime('now')
"""


def upsert_job(job: JobRecord) -> str:
    params = _job_params(job)
    with db() as conn:
        conn.execute(_UPSERT_JOB_SQL, params)
    return params[0]


def upsert_jobs(jobs: list[JobRecord]) -> int:
    """Batch upsert: ONE connection, ONE transaction, ONE init_db() for the whole
    list. The per-job version re-ran the entire migration ladder on every row,
    which is thousands of redundant schema executions on a 2-hourly ingest."""
    if not jobs:
        return 0
    # Last-wins de-dupe by canonical id so a digest cannot INSERT the same id twice.
    by_id: dict[str, JobRecord] = {}
    for job in jobs:
        jid = job.job_id or job_id_from_url(job.url)
        if jid:
            by_id[jid] = job
    jobs = list(by_id.values())
    with db() as conn:
        # If a URL already exists under a different id (identity-key change, e.g.
        # Glassdoor now hashes jobListingId), keep the existing PK so FK rows in
        # pipeline/eval_results stay valid — only refresh the content.
        for job in jobs:
            jid = job.job_id or job_id_from_url(job.url)
            row = conn.execute(
                "SELECT id FROM jobs WHERE url = ? AND id != ?",
                (job.url, jid),
            ).fetchone()
            if row:
                job.job_id = row["id"]
        rows = [_job_params(j) for j in jobs]
        # Re-dedupe in case two new ids remapped onto the same existing PK.
        seen: set[str] = set()
        deduped_rows: list[tuple] = []
        for row in reversed(rows):
            if row[0] in seen:
                continue
            seen.add(row[0])
            deduped_rows.append(row)
        deduped_rows.reverse()
        conn.executemany(_UPSERT_JOB_SQL, deduped_rows)
    return len(deduped_rows)


def add_jobs_to_pipeline(job_ids: list[str], status: str = "pending") -> int:
    """Batched counterpart to add_to_pipeline (INSERT OR IGNORE, so re-ingest is a no-op)."""
    if not job_ids:
        return 0
    with db() as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO pipeline (job_id, status) VALUES (?, ?)",
            [(jid, status) for jid in job_ids],
        )
    return len(job_ids)


def start_run(dry_run: bool = False) -> str:
    run_id = str(uuid.uuid4())[:8]
    with db() as conn:
        conn.execute(
            "INSERT INTO runs (run_id, started_at, dry_run) VALUES (?, ?, ?)",
            (run_id, datetime.now(timezone.utc).isoformat(), int(dry_run)),
        )
    return run_id


def finish_run(
    run_id: str,
    *,
    source_stats: dict,
    discovered: int,
    passed: int,
    strong_fit: int,
    error: str = "",
) -> None:
    with db() as conn:
        conn.execute(
            """
            UPDATE runs SET finished_at=?, source_stats_json=?, jobs_discovered=?,
            jobs_passed_filter=?, jobs_strong_fit=?, error=?
            WHERE run_id=?
            """,
            (
                datetime.now(timezone.utc).isoformat(),
                json.dumps(source_stats),
                discovered,
                passed,
                strong_fit,
                error,
                run_id,
            ),
        )


def get_last_run() -> dict | None:
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM runs ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None


def pending_pipeline_count() -> int:
    """Pending rows that still match the live profile (title + fit floor)."""
    from store.status import pipeline_status_counts

    return int(pipeline_status_counts(targeted=True).get("pending") or 0)


def pipeline_breakdown() -> dict[str, int]:
    from store.status import pipeline_status_counts

    return pipeline_status_counts(targeted=True)


def add_to_pipeline(job_id: str, status: str = "pending") -> None:
    with db() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO pipeline (job_id, status) VALUES (?, ?)
            """,
            (job_id, status),
        )


def audit(action: str, resource_type: str = "", resource_id: str = "", details: dict | None = None) -> None:
    with db() as conn:
        conn.execute(
            """
            INSERT INTO audit_log (action, resource_type, resource_id, details_json)
            VALUES (?, ?, ?, ?)
            """,
            (action, resource_type, resource_id, json.dumps(details or {})),
        )


# How long a claimed task may stay 'running' before the worker that claimed it
# is presumed dead.
STALE_TASK_MINUTES = 30


def reap_stale_tasks(conn: sqlite3.Connection) -> int:
    """Fail tasks left 'running' by a worker process that no longer exists.

    Nothing moves a row out of 'running' except the worker that claimed it, so an
    API restart mid-scan strands it — and a stranded discover blocks every later
    one twice over: `enqueue_task` hands back the dead row's id instead of
    queueing, and `_claim_pending` cancels new pending discovers while one is
    "running". That is why the Scan button span for a day and no scan could
    start again.

    A full multi-board scan takes minutes, so 30 is generous: reaping too early
    costs a duplicate scan, never reaping costs the feature.

    `started_at` is NULL on rows claimed before that column existed; those fall
    back to `created_at`. The comparison is in SQLite's datetime format on
    purpose — an isoformat() string sorts above it and would never match.
    """
    cur = conn.execute(
        """
        UPDATE worker_queue
        SET status = 'failed',
            attempts = attempts + 1,
            processed_at = datetime('now')
        WHERE status = 'running'
          AND COALESCE(started_at, created_at) < datetime('now', ?)
        """,
        (f"-{STALE_TASK_MINUTES} minutes",),
    )
    return int(cur.rowcount or 0)


def enqueue_task(task_type: str, payload: dict) -> int:
    with db() as conn:
        # One discover at a time — a second Scan click should not stack scrapes.
        # Reap first: a task stranded 'running' by a dead worker would otherwise
        # match here forever, so every future Scan click was answered with the
        # dead row's id and silently discarded.
        reap_stale_tasks(conn)
        if task_type == "discover":
            existing = conn.execute(
                """
                SELECT id FROM worker_queue
                WHERE task_type = 'discover' AND status IN ('pending', 'running')
                ORDER BY id DESC LIMIT 1
                """
            ).fetchone()
            if existing:
                return int(existing["id"])
        cur = conn.execute(
            "INSERT INTO worker_queue (task_type, payload_json) VALUES (?, ?)",
            (task_type, json.dumps(payload)),
        )
        return int(cur.lastrowid)
