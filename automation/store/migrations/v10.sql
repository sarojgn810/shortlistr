-- v10: auth_challenges — proof-of-possession for a phone number.
--
-- The platform's identity is a phone number. Until now a caller simply asserted
-- one in a request body and was believed. A challenge is how that assertion gets
-- checked: a short-lived code is delivered over a channel only the real owner of
-- the number can read, and redeeming it mints a session token.
--
-- Only the hash is stored. A challenge table in plaintext is a list of live
-- credentials, and this database is already the most sensitive thing we hold.
--
-- attempts exists so a six-digit code cannot be brute-forced: a million guesses
-- is minutes of scripted traffic, five guesses is not. expires_at keeps the
-- window small enough that an intercepted code is stale before it is useful.

CREATE TABLE IF NOT EXISTS auth_challenges (
    phone       TEXT PRIMARY KEY,
    code_hash   TEXT NOT NULL,
    expires_at  TEXT NOT NULL,
    attempts    INTEGER NOT NULL DEFAULT 0,
    issued_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_auth_challenges_expiry ON auth_challenges(expires_at);
