-- Schema v6: engage sessions (candidate conversation state — testbed now, WhatsApp later)

CREATE TABLE IF NOT EXISTS engage_sessions (
    phone TEXT PRIMARY KEY,               -- the identity (no logins by design)
    state TEXT NOT NULL DEFAULT 'new',
    data TEXT NOT NULL DEFAULT '{}',      -- JSON: name, employer, consent_at, matches, last_artifact
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
