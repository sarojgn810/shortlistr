-- Schema v2: application receipts + status indexes

CREATE TABLE IF NOT EXISTS application_receipts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id INTEGER REFERENCES applications(id),
    job_id TEXT NOT NULL REFERENCES jobs(id),
    channel TEXT NOT NULL CHECK (channel IN ('email', 'prep', 'manual', 'ats_assist')),
    fields_json TEXT NOT NULL DEFAULT '{}',
    resume_path TEXT,
    cover_letter_text TEXT,
    submitted_at TEXT NOT NULL DEFAULT (datetime('now')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_receipts_job_id ON application_receipts(job_id);
CREATE INDEX IF NOT EXISTS idx_receipts_submitted ON application_receipts(submitted_at);
CREATE INDEX IF NOT EXISTS idx_pipeline_status ON pipeline(status);
CREATE INDEX IF NOT EXISTS idx_applications_job_id ON applications(job_id);
CREATE INDEX IF NOT EXISTS idx_applications_status ON applications(status);
