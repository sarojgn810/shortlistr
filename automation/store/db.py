"""SQLite job store — system of record for Phase 1."""

from __future__ import annotations

import json
import os
import socket
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

from config import DATA_DIR
from models.job import JobRecord, job_id_from_url

DB_PATH = os.path.join(DATA_DIR, "shortlistr.db")
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")
MIGRATIONS_DIR = os.path.join(os.path.dirname(__file__), "migrations")

# One database. `data/shortlistr.db` is the owner's own job search — discovery
# inbox, evaluations, applications — and there is nothing else. The engine used
# to carry a second "platform" store for Layer 3 (candidate sessions, referrals,
# referrers); that product is its own repo now, so the scope switch is gone.
# Nothing here should ever open a database belonging to somebody else.


LEGACY_DB_PATH = os.path.join(DATA_DIR, "autojob.db")


def active_db_path() -> str:
    """Resolved at call time so tests that monkeypatch DB_PATH stay isolated.

    An install that predates the rename has its whole job history in
    `data/autojob.db`. Adopt it rather than silently starting an empty
    `shortlistr.db` beside it — that would look exactly like data loss. Only ever
    when the new path does not already exist, so this cannot clobber anything.
    """
    if not os.path.exists(DB_PATH) and os.path.exists(LEGACY_DB_PATH):
        try:
            os.rename(LEGACY_DB_PATH, DB_PATH)
            for suffix in ("-wal", "-shm"):
                if os.path.exists(LEGACY_DB_PATH + suffix):
                    os.rename(LEGACY_DB_PATH + suffix, DB_PATH + suffix)
        except OSError:
            return LEGACY_DB_PATH  # read it where it is rather than fail to open
    return DB_PATH


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
        version = 16
    if version < 17:
        # Drop the referral-desk tables. They belong to the referral engine,
        # which is its own repo; nothing here reads them. The v5/v11/v12/v14
        # steps that built them stay in the ladder — this drop just comes after.
        v17_path = os.path.join(MIGRATIONS_DIR, "v17.sql")
        if os.path.exists(v17_path):
            conn.executescript(open(v17_path, encoding="utf-8").read())
        conn.execute("UPDATE schema_version SET version = 17")
        version = 17
    if version < 18:
        # Who holds a claim, and when they last proved they were alive. Without
        # these, a task stranded by a killed worker could only be spotted by a
        # 30-minute timer — see reap_stale_tasks.
        _add_column_if_missing(conn, "worker_queue", "owner", "TEXT")
        _add_column_if_missing(conn, "worker_queue", "heartbeat_at", "TEXT")
        conn.execute("UPDATE schema_version SET version = 18")
        version = 18
    if version < 19:
        # Follow-ups: mail saying an application of yours needs action, including
        # for applications made outside this tool, which the job-centric tracker
        # board has no row for.
        v19_path = os.path.join(MIGRATIONS_DIR, "v19.sql")
        if os.path.exists(v19_path):
            conn.executescript(open(v19_path, encoding="utf-8").read())
        conn.execute("UPDATE schema_version SET version = 19")


def _connect() -> sqlite3.Connection:
    os.makedirs(DATA_DIR, exist_ok=True)
    # active_db_path(), not DB_PATH: it reads DB_PATH at call time, so a test that
    # monkeypatches the module attribute still redirects connections opened here.
    # timeout=30: wait for writers (scan/upsert) instead of failing list_jobs with
    # "database is locked" mid-discover — that 500 emptied Discover and made the
    # count bounce up and down.
    conn = sqlite3.connect(active_db_path(), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    # WAL lets readers proceed while a scanner writes.
    try:
        conn.execute("PRAGMA journal_mode = WAL")
    except sqlite3.Error:
        pass
    return conn


# Paths that have completed schema + migrations in this process. Re-running the
# full ladder on every `db()` open contended with discovery writers.
_initialized_dbs: set[str] = set()


def _migrate_lock_path(db_path: str) -> str:
    return db_path + ".migrate.lock"


def init_db() -> None:
    """Create/migrate schema once per process; serialize across processes on first boot.

    Fresh installs start API + scheduler together; both used to run migrations at
    once and surface ``database is locked`` on Discover. A blocking file lock
    makes the second waiter use the already-migrated file.
    """
    path = os.path.abspath(active_db_path())
    if path in _initialized_dbs and os.path.isfile(path):
        return

    from store import filelock

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    lock_path = _migrate_lock_path(path)
    with open(lock_path, "w") as lock_fh:
        filelock.acquire(lock_fh)
        try:
            # Another process may have finished while we waited.
            if path in _initialized_dbs and os.path.isfile(path):
                return
            with _connect() as conn:
                conn.executescript(open(SCHEMA_PATH, encoding="utf-8").read())
                if _schema_version(conn) == 0:
                    conn.execute("INSERT INTO schema_version (version) VALUES (1)")
                _run_migrations(conn)
                conn.execute(
                    "INSERT OR IGNORE INTO tenants (id, name) VALUES ('default', 'default')"
                )
                conn.commit()
            _initialized_dbs.add(path)
        finally:
            filelock.release(lock_fh)


@contextmanager
def db():
    init_db()
    conn = _connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


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
HEARTBEAT_SECONDS = 15
HEARTBEAT_STALE_SECONDS = 90

# Who this process is, for the `owner` column. Only ever read by a human staring
# at a stuck queue — liveness is decided by the heartbeat, not by this string,
# because a pid can be recycled and `os.kill(pid, 0)` is not a liveness probe on
# Windows, which CI runs.
WORKER_ID = f"{socket.gethostname()}:{os.getpid()}"


def touch_task_heartbeat(task_id: int) -> None:
    """Say 'still working' for a claimed task. Cheap: one indexed UPDATE."""
    with db() as conn:
        conn.execute(
            "UPDATE worker_queue SET heartbeat_at = datetime('now') "
            "WHERE id = ? AND status = 'running'",
            (task_id,),
        )


def reap_stale_tasks(conn: sqlite3.Connection) -> int:
    """Fail tasks left 'running' by a worker that is gone.

    Nothing moves a row out of 'running' except the worker that claimed it, and
    the workers are daemon threads — Python kills those outright when the process
    exits, so no `finally` runs and the claim is never released. `make api` runs
    under --reload, so any saved file restarts the server; a scan takes minutes,
    so the window is wide. A stranded discover then blocks every later one twice
    over: `enqueue_task` hands back the dead row's id instead of queueing, and
    `_claim_pending` cancels new pending discovers while one is "running". That
    is why the Scan button span for a day and no scan could start again.

    A live worker heartbeats every HEARTBEAT_SECONDS, so silence for
    HEARTBEAT_STALE_SECONDS means the process is gone and the row is free. That
    is a real liveness signal rather than a guess, and it cuts the dead zone from
    30 minutes to about a minute.

    Rows with no heartbeat at all — claimed before v18, or by something that does
    not heartbeat — still fall back to the old age check, so this can only ever
    reap more than before, never less.

    Comparisons are in SQLite's datetime format on purpose: an isoformat() string
    sorts above it and would silently never match.
    """
    cur = conn.execute(
        """
        UPDATE worker_queue
        SET status = 'failed',
            attempts = attempts + 1,
            processed_at = datetime('now')
        WHERE status = 'running'
          AND (
                (heartbeat_at IS NOT NULL AND heartbeat_at < datetime('now', ?))
             OR (heartbeat_at IS NULL
                 AND COALESCE(started_at, created_at) < datetime('now', ?))
          )
        """,
        (f"-{HEARTBEAT_STALE_SECONDS} seconds", f"-{STALE_TASK_MINUTES} minutes"),
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
