-- v17 — retire the referral-desk (Layer 3) tables.
--
-- Referrals, referrers, candidate engagement sessions and Telegram links belong
-- to the referral engine, which lives in its own repo. Nothing in this
-- single-user tool reads or writes them: the last reference was a NOT EXISTS
-- guard in purge_archived(), removed alongside this migration.
--
-- The v5/v11/v12/v14 steps that created and altered these tables are left in
-- the ladder on purpose. Migrations are a version ladder — an existing database
-- still has to be able to walk v1..v17 in order, so the create stays and this
-- drop comes after it.
--
-- Safe on a personal database: these tables are empty there by construction.
-- Anyone who was running the platform side keeps their data in data/platform.db,
-- which this engine no longer opens.

DROP TABLE IF EXISTS referrals;
DROP TABLE IF EXISTS referrers;
DROP TABLE IF EXISTS engage_sessions;
DROP TABLE IF EXISTS telegram_links;
