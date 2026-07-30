-- v11 — a referral belongs to somebody.
--
-- Platform database only; the personal instance never writes referrals.
--
-- Until now a referral recorded candidate → job @ company and nothing about
-- WHICH human agreed to walk it in. That absence was not neutral:
--
--   * registry.inbox(phone) had to filter by company, so every referrer at a
--     company saw every candidate for it — the same names, phone numbers and
--     resume links. A candidate consenting to "a referrer at Wipro" got all of
--     them.
--   * Two referrers could submit the same person for the same requisition,
--     which at most employers voids both bonuses.
--   * Nobody owned any given candidate, so everyone could assume somebody else
--     would act.
--   * Nobody could be paid, because the ledger could not say who did the work.
--
-- referrer_id is NULL for the rows that predate this, which is honest: those
-- referrals were walked in by the operator, and the ledger genuinely does not
-- know who else touched them. Do not backfill a guess.
--
-- The columns are added by _add_column_if_missing in db.py, not here — SQLite
-- has no ADD COLUMN IF NOT EXISTS and a half-applied migration must re-run
-- safely. This file holds only what is idempotent on its own.

-- Finding the claimed/unclaimed rows for one referrer, which is what the inbox
-- asks on every load.
CREATE INDEX IF NOT EXISTS idx_referrals_referrer ON referrals(referrer_id);

-- First-accept-wins needs to ask "is this candidate already claimed for this
-- job" cheaply, and the answer has to be the same for everyone racing.
CREATE INDEX IF NOT EXISTS idx_referrals_claim ON referrals(job_ref, status);

-- One person is not referred for the same requisition twice, whoever claims it.
-- Partial, because cancelled and expired rows are re-routable by design — the
-- state machine allows expired → routed, and a duplicate check that counted
-- dead rows would block the retry it exists to permit.
CREATE UNIQUE INDEX IF NOT EXISTS idx_referrals_no_duplicate
    ON referrals(candidate_phone, job_ref)
    WHERE candidate_phone != ''
      AND status NOT IN ('cancelled', 'expired', 'rejected');
