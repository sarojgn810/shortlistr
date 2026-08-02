-- v12 — an outbox, so the system can speak first.
--
-- Platform database only.
--
-- Until now nothing could reach a person who was not currently typing. A
-- referrer claimed a candidate: silence. A candidate's CV was ready: silence.
-- A referral expired after seven days: silence. Two of the three live sessions
-- were stranded mid-flow with a tailored CV waiting and no way to say so.
--
-- A queue rather than a direct send, for three reasons that all cost something
-- if ignored:
--
--   * No channel is configured yet. Sending directly would mean the decision to
--     notify is lost the moment it cannot be delivered; queued, the backlog is
--     waiting when a channel arrives.
--   * Delivery failure must never break a conversation. Enqueue happens inside
--     the request, delivery does not.
--   * Somebody will eventually ask what we told a candidate and when. A row
--     answers that; a fire-and-forget call does not.
--
-- `dedupe_key` is what stops the same person being told the same thing twice
-- when a sweep re-runs. It is nullable because some messages are genuinely
-- repeatable.

CREATE TABLE IF NOT EXISTS notifications (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    recipient     TEXT NOT NULL,           -- phone slug, or an email address
    channel       TEXT NOT NULL DEFAULT 'auto',   -- auto | email | whatsapp
    kind          TEXT NOT NULL,           -- what happened, for grouping
    subject       TEXT NOT NULL DEFAULT '',
    body          TEXT NOT NULL,
    dedupe_key    TEXT,
    status        TEXT NOT NULL DEFAULT 'queued', -- queued | sent | failed | dropped
    attempts      INTEGER NOT NULL DEFAULT 0,
    last_error    TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    sent_at       TEXT
);

-- The drain reads this on every tick.
CREATE INDEX IF NOT EXISTS idx_notifications_pending
    ON notifications(status, created_at);

-- Told once, not once per sweep.
CREATE UNIQUE INDEX IF NOT EXISTS idx_notifications_dedupe
    ON notifications(dedupe_key) WHERE dedupe_key IS NOT NULL;

-- "What have we sent this person" — asked by support and by DPDP requests.
CREATE INDEX IF NOT EXISTS idx_notifications_recipient
    ON notifications(recipient, created_at);
