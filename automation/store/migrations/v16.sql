-- Contact-resolution layer (job → person → verified email candidates).
-- Auditable evidence; never auto-sends.

CREATE TABLE IF NOT EXISTS cr_company (
    company_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    name_key TEXT NOT NULL UNIQUE,
    email_domain TEXT,
    website_domain TEXT,
    mx_provider TEXT,
    is_catch_all INTEGER,
    country TEXT,
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS cr_email_pattern (
    company_id INTEGER NOT NULL,
    pattern TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0,
    sample_count INTEGER NOT NULL DEFAULT 0,
    source_list TEXT DEFAULT '',
    learned_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (company_id, pattern),
    FOREIGN KEY (company_id) REFERENCES cr_company(company_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS cr_person (
    person_id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER,
    job_id TEXT,
    full_name TEXT NOT NULL,
    first_name TEXT,
    last_name TEXT,
    title TEXT DEFAULT '',
    seniority_rank INTEGER,
    linkedin_url TEXT DEFAULT '',
    github_login TEXT DEFAULT '',
    source TEXT NOT NULL,
    discovery_conf REAL NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (company_id) REFERENCES cr_company(company_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_cr_person_job ON cr_person(job_id);
CREATE INDEX IF NOT EXISTS idx_cr_person_company ON cr_person(company_id);

CREATE TABLE IF NOT EXISTS cr_email_candidate (
    email_id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER NOT NULL,
    job_id TEXT,
    email TEXT NOT NULL,
    gen_method TEXT NOT NULL,
    pattern_conf REAL DEFAULT 0,
    verify_status TEXT DEFAULT 'unknown',
    verify_source TEXT DEFAULT '',
    source_count INTEGER DEFAULT 1,
    final_score REAL DEFAULT 0,
    decision TEXT DEFAULT 'REVIEW',
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (person_id) REFERENCES cr_person(person_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_cr_email_job ON cr_email_candidate(job_id);

CREATE TABLE IF NOT EXISTS cr_evidence (
    evidence_id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    entity_id INTEGER NOT NULL,
    kind TEXT NOT NULL,
    value TEXT DEFAULT '',
    url TEXT DEFAULT '',
    observed_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_cr_evidence_entity ON cr_evidence(entity_type, entity_id);

CREATE TABLE IF NOT EXISTS cr_job_resolution (
    job_id TEXT PRIMARY KEY,
    company_id INTEGER,
    status TEXT DEFAULT 'pending',
    best_person_id INTEGER,
    best_email_id INTEGER,
    summary_json TEXT DEFAULT '{}',
    resolved_at TEXT,
    FOREIGN KEY (company_id) REFERENCES cr_company(company_id) ON DELETE SET NULL
);
