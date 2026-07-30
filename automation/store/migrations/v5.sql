-- Schema v5: routed-referral log (Referral Engine M1 — source of truth for
-- referral→interview conversion; see docs/memory/decisions.md)

CREATE TABLE IF NOT EXISTS referrals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id TEXT NOT NULL DEFAULT 'default',
    candidate_name TEXT NOT NULL,
    candidate_phone TEXT NOT NULL DEFAULT '',
    job_ref TEXT NOT NULL,                        -- free text: "role @ company"
    channel TEXT NOT NULL DEFAULT 'anchor',       -- anchor | network
    resume_kind TEXT NOT NULL DEFAULT 'raw',      -- raw | tailored
    resume_ref TEXT NOT NULL DEFAULT '',          -- path/version of the resume sent
    status TEXT NOT NULL DEFAULT 'routed',
    referred_at TEXT NOT NULL,                    -- ISO date the referral was routed
    accepted_at TEXT,                             -- set on → accepted
    interviewed_at TEXT,                          -- set on → interviewing (survives terminal states)
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    notes TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_referrals_status ON referrals(status);
CREATE INDEX IF NOT EXISTS idx_referrals_referred_at ON referrals(referred_at);

-- One ACTIVE referral per (candidate, job); closed ones don't block a re-route.
CREATE UNIQUE INDEX IF NOT EXISTS idx_referrals_active_unique
    ON referrals(candidate_name, job_ref)
    WHERE status NOT IN ('rejected', 'expired', 'cancelled');
