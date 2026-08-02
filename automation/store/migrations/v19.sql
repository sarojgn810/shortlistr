-- v19 — follow-ups: things the mailbox says you need to act on.
--
-- The tracker board is job-centric: pipeline JOIN jobs LEFT JOIN applications.
-- That works for anything discovered here, and not at all for the case this
-- table exists for — "Questionnaire still pending from Virtana", where the user
-- applied outside the tool. There is no job row, so there can be no application
-- row, so the board has nowhere to put it and the signal was simply lost.
--
-- job_id and application_id are nullable on purpose: a follow-up may be tied to
-- something the tracker already knows, or to nothing at all. Neither is a
-- foreign key, so purging an archived job can never delete the user's evidence
-- that an application is live.

CREATE TABLE IF NOT EXISTS follow_ups (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    kind           TEXT NOT NULL,              -- application_update, invite_to_apply
    company        TEXT NOT NULL DEFAULT '',
    role           TEXT NOT NULL DEFAULT '',
    subject        TEXT NOT NULL DEFAULT '',
    sender         TEXT NOT NULL DEFAULT '',
    source         TEXT NOT NULL DEFAULT 'email',
    job_id         TEXT,
    application_id INTEGER,
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    resolved_at    TEXT
);

-- One open follow-up per company per kind. Cutshort sends the same questionnaire
-- reminder three times a week; three identical rows is nagging, not tracking.
CREATE UNIQUE INDEX IF NOT EXISTS follow_ups_open_unique
    ON follow_ups (kind, company) WHERE resolved_at IS NULL;

CREATE INDEX IF NOT EXISTS follow_ups_open ON follow_ups (resolved_at, created_at);
