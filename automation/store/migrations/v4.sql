-- Schema v4: long-term agent memory (learnings)

CREATE TABLE IF NOT EXISTS learnings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id TEXT NOT NULL DEFAULT 'default',
    kind TEXT NOT NULL DEFAULT 'insight',      -- insight | preference | outcome | pattern
    key TEXT,                                   -- short slug for dedupe/lookup
    insight TEXT NOT NULL,
    confidence INTEGER NOT NULL DEFAULT 5,      -- 1-10
    source TEXT NOT NULL DEFAULT 'observed',    -- observed | user-stated | inferred
    refs TEXT,                                   -- JSON array of related ids/urls
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_learnings_tenant ON learnings(tenant_id);
CREATE INDEX IF NOT EXISTS idx_learnings_kind ON learnings(kind);
