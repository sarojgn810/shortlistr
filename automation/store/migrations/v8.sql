-- Schema v8: moderation for user-submitted jobs
--
-- Anyone can share a job (a LinkedIn post, a careers page, an internal list), so
-- user-submitted rows are held for admin review before candidates ever see them.
-- Scraped rows keep review_status NULL and stay auto-trusted.
--
-- ALTER TABLE statements live in store/db.py::_add_column_if_missing (SQLite has
-- no ADD COLUMN IF NOT EXISTS and a half-applied migration must re-run safely).

CREATE INDEX IF NOT EXISTS idx_jobs_review ON jobs(review_status);
CREATE INDEX IF NOT EXISTS idx_jobs_referrer_phone ON jobs(referrer_phone);
