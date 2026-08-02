-- Schema v7: job lifecycle (archive/liveness) + referrer registry + referral job identity
--
-- NOTE: the ALTER TABLE ADD COLUMN statements for this migration live in
-- store/db.py::_add_column_if_missing (SQLite has no ADD COLUMN IF NOT EXISTS, and a
-- partially-applied migration must be safe to re-run). Only idempotent DDL lives here.

-- People who can refer candidates into their own employer. One row per (person, company);
-- a person can be a candidate AND a referrer — roles are relationships, not identity.
CREATE TABLE IF NOT EXISTS referrers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone TEXT NOT NULL,                     -- same identity as engage_sessions.phone
    name TEXT NOT NULL DEFAULT '',
    company TEXT NOT NULL,
    company_norm TEXT NOT NULL,              -- engage.core._norm_company(company)
    status TEXT NOT NULL DEFAULT 'offered',  -- offered | active | declined
    source TEXT NOT NULL DEFAULT 'chat',     -- chat | founder
    verified_at TEXT,
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_referrers_phone_company ON referrers(phone, company_norm);
CREATE INDEX IF NOT EXISTS idx_referrers_company ON referrers(company_norm);
CREATE INDEX IF NOT EXISTS idx_referrers_status ON referrers(status);

-- Candidate matching and the liveness sweep both query these.
CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company);
CREATE INDEX IF NOT EXISTS idx_jobs_archived ON jobs(archived_at);
CREATE INDEX IF NOT EXISTS idx_jobs_checked ON jobs(last_checked_at);
CREATE INDEX IF NOT EXISTS idx_referrals_job ON referrals(job_id);
