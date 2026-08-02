-- shortlistr SQLite schema v1

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    url TEXT NOT NULL UNIQUE,
    source TEXT NOT NULL,
    company TEXT,
    title TEXT,
    location TEXT,
    jd_text TEXT,
    salary TEXT,
    department TEXT,
    company_email TEXT,
    status TEXT DEFAULT 'New',
    email_sent TEXT DEFAULT 'No',
    notes TEXT DEFAULT '',
    fit_score INTEGER DEFAULT 0,
    fit_reason TEXT DEFAULT '',
    discovered_at TEXT,
    metadata_json TEXT DEFAULT '{}',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_source ON jobs(source);
CREATE INDEX IF NOT EXISTS idx_jobs_discovered ON jobs(discovered_at);

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    dry_run INTEGER DEFAULT 0,
    source_stats_json TEXT DEFAULT '{}',
    jobs_discovered INTEGER DEFAULT 0,
    jobs_passed_filter INTEGER DEFAULT 0,
    jobs_strong_fit INTEGER DEFAULT 0,
    error TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS pipeline (
    job_id TEXT PRIMARY KEY REFERENCES jobs(id),
    status TEXT DEFAULT 'pending',
    added_at TEXT DEFAULT (datetime('now')),
    evaluated_at TEXT,
    FOREIGN KEY (job_id) REFERENCES jobs(id)
);

CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT REFERENCES jobs(id),
    company TEXT,
    role TEXT,
    score REAL,
    status TEXT,
    applied_date TEXT,
    report_path TEXT,
    notes TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id TEXT DEFAULT 'default',
    actor TEXT DEFAULT 'system',
    action TEXT NOT NULL,
    resource_type TEXT,
    resource_id TEXT,
    details_json TEXT DEFAULT '{}',
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS eval_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT REFERENCES jobs(id),
    schema_version TEXT,
    score REAL,
    legitimacy TEXT,
    result_json TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS worker_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_type TEXT NOT NULL,
    payload_json TEXT,
    status TEXT DEFAULT 'pending',
    attempts INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    processed_at TEXT
);

CREATE TABLE IF NOT EXISTS tenants (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    tenant_id TEXT REFERENCES tenants(id),
    email TEXT UNIQUE,
    role TEXT DEFAULT 'owner',
    created_at TEXT DEFAULT (datetime('now'))
);
