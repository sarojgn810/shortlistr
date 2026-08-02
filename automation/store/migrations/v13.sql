-- v13 — a role can be listed without naming the employer.
--
-- Platform database only.
--
-- A referrer will often share an opening they are happy to refer into but not
-- happy to have posted publicly under their employer's name — an unadvertised
-- requisition, a team that has not announced it is hiring, or simply not
-- wanting their company associated with a job board. Losing those roles is
-- losing the referable inventory the whole product runs on.
--
-- Two columns and one rule:
--
--   company_confidential   do not show the name while browsing
--   company_hint           what to show instead: "MNC · 10,000+ employees"
--
-- THE RULE: this is presentation only. `company` keeps the real employer, and
-- every matcher, filter and gate keeps reading it. The confidentiality gate
-- compares a candidate's own employer against `company` — blanking it to hide
-- the name would mean a candidate at that firm starts seeing their own
-- employer's unadvertised roles. A privacy feature causing a privacy leak.
--
-- The hiding also lifts before the candidate approves anything. Nobody can
-- consent to their CV being sent to a company they have not been told the name
-- of, so the reveal happens when they pick the role, not after.

-- Column additions live in db.py (_add_column_if_missing); SQLite has no
-- ADD COLUMN IF NOT EXISTS and a half-applied migration must re-run safely.

-- Browsing filters on this constantly once any role uses it.
CREATE INDEX IF NOT EXISTS idx_jobs_confidential
    ON jobs(company_confidential) WHERE company_confidential = 1;
