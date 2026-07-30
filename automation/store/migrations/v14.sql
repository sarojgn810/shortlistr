-- v14 — a Telegram chat is a person we can reach.
--
-- Platform database only.
--
-- WhatsApp needs a BSP, and a BSP takes weeks of business verification before
-- the first message can be sent. Telegram needs a token from @BotFather and
-- costs nothing, so the parts of this product that have never been exercised by
-- a real person — the conversation, the notifications, the referrer inbox — can
-- be tested this week instead of next quarter.
--
-- Two properties make it more than a stopgap:
--
--   * The bot LONG-POLLS. The laptop dials out to Telegram; nothing dials in.
--     No public bind, no tunnel, no open port — so a live test with real people
--     does not require the hosting blockers to be cleared first.
--   * Telegram will hand over a phone number the user taps to share, and it is
--     verified by Telegram. That is the same trust shape as a BSP webhook: the
--     platform is vouching for the number, not the person typing it.
--
-- The phone remains the identity, deliberately. Everything downstream — the
-- session, the ledger, the artifacts, the referrer registry — keys on the phone
-- slug, and giving Telegram its own parallel identity would fork all of it. So
-- this table is a link, not an account.

CREATE TABLE IF NOT EXISTS telegram_links (
    chat_id     INTEGER PRIMARY KEY,     -- Telegram's id for the conversation
    phone       TEXT,                    -- the phone slug, once they share it
    username    TEXT,
    first_name  TEXT,
    verified_at TEXT,                    -- when Telegram vouched for the number
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Outbound delivery asks "which chat reaches this person" on every queued row.
CREATE INDEX IF NOT EXISTS idx_telegram_links_phone ON telegram_links(phone);
