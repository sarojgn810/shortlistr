-- v9: artifacts — who is allowed to download which generated file.
--
-- Until now /engage/artifact took a filesystem path and authorized it by
-- checking the path sat under the output root. That is a containment check, not
-- an ownership check: any caller could fetch any candidate's tailored resume by
-- naming its path. This table is the ownership record that replaces it.
--
-- `id` is an opaque random token, never a rowid — it appears in the download URL,
-- so a sequential id would simply restore enumeration by another route.
--
-- `owner_phone` empty means nobody may fetch it over the candidate API. Files
-- the operator batch-tailored for people who never opened a chat session are
-- exactly that case, and they stay operator-only.
--
-- `path` is relative to the platform data root, so the rows survive the move
-- from a laptop to a server. When storage becomes object storage rather than a
-- volume, this column is the only thing that changes.

CREATE TABLE IF NOT EXISTS artifacts (
    id          TEXT PRIMARY KEY,
    owner_phone TEXT NOT NULL DEFAULT '',
    path        TEXT NOT NULL,
    kind        TEXT NOT NULL DEFAULT 'resume',   -- resume | report | preview
    job_ref     TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- One row per file: re-tailoring the same JD for the same candidate overwrites
-- the file, and must reuse the row rather than mint a second id for it.
CREATE UNIQUE INDEX IF NOT EXISTS idx_artifacts_path  ON artifacts(path);
CREATE INDEX        IF NOT EXISTS idx_artifacts_owner ON artifacts(owner_phone);
