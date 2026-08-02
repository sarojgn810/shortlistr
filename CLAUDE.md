# CLAUDE.md — Shortlistr engine session context

**Read this first, every session.** It is the always-loaded context for working on
this repo. Keep it under ~400 lines and high-signal. When something here goes stale,
fix it in the same PR that made it stale.

Companion docs (read on demand, linked from here):
- [AGENTS.md](AGENTS.md) — data contract + skill modes (do not violate the data contract)
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — deep layout, data flow
- [docs/memory/](docs/memory/) — durable project memory (decisions, incidents/RCAs)

---

## What we're building

**Shortlistr** — a local-first, judgment-first job-search tool. It discovers roles,
evaluates each one (A–G blocks + legitimacy), lets the user approve before
applying, then tracks outcomes. Quality over blast radius — **no volume
counters, never auto-submit**. Everything runs on the user's machine; no cloud
accounts required.

**This repo is single-user.** Anyone who clones it gets a complete personal job
search. Multi-party / referral products are out of scope here and no longer have
a foothold: the referral desk lives in its own repo, and v17 dropped its tables.
Do not reintroduce a second database, a "platform" scope, or any table that holds
another person's data.

Nothing in this repo may acquire an outbound path, a server URL, or the concept
of one. A change here that would let a cloner send us anything is wrong however
convenient it looks — including in the dashboard, which is the tempting place
for it because it already reads `shortlistr.db`.

**"Done" for a change means:** the behavior works in a real manual run, has tests that
mirror that flow, `make test` is green, `cd dashboard && npx tsc --noEmit` is clean, and
you can explain the diff in one or two sentences.

**Layer rule.** This repo is Layers 1 (engine: `sources/`, `scrapers/`, `eval/`,
`cv/`, `llm/`, `store/`, `processors/`) and 2 (the single-user tool: onboarding,
inbox, pipeline, apply, dashboard). Concepts of "many users" belong elsewhere.

---

## Stack (one-liner each)

- **Backend:** Python + FastAPI, served by uvicorn at `http://127.0.0.1:8787` (`make api`).
  Package root is `automation/`. CLI is `python -m automation.cli`.
- **Store:** SQLite at `data/shortlistr.db` (`automation/store/`), schema_version **19**.
  One database, no scope switch — see the single-user note above.
- **Frontend:** Next.js 15 (App Router) + TypeScript + Tailwind, at `http://localhost:3000`
  (`make dashboard-dev`). Calls the API through the `/api` rewrite.
- **Browser automation:** Playwright/Chromium — résumé PDF render + apply-assist form fill.
- **LLM:** `automation/llm/` — anthropic, openai, gemini, **grok** (xAI), **groq**
  (groq.com Llama), ollama. Currently `groq` / `llama-3.3-70b-versatile`.
- **OCR:** tesseract + pytesseract, for reading openings out of shared screenshots.
- **Config:** `config/profile.yml` (job targeting, LLM provider) + `portals.yml` (companies).
  Secrets live in `.env` / OS keychain via `automation/secrets_store.py`.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full picture.

---

## Critical flows that must never break

If a change touches any of these, manually verify the whole flow and add/keep a test.

**Engine flows**

1. **Discovery → inbox.** Sources → `passes_title_location()` filter → persist → inbox.
   Targeting comes from the user's profile (titles + locations). Empty profile falls back
   to a default keyword set. `make api` must boot even with no profile.
2. **Evaluate → approve → apply.** Pipeline state machine in `automation/store/status.py`:
   `pending → evaluated → approved → submitted` (+ `skipped`, + backward undo transitions).
   Nothing is submitted without explicit user action.
3. **Profile save → live retarget.** `save_profile_from_ui()` writes `config/profile.yml` +
   `.env` key, then calls `reload_discovery_config()` and `reload_llm_config()` so the next
   scan uses the new targeting **without an API restart**.
4. **Résumé upload → ingest.** `/cv/upload` writes `cv.md` + `resume.pdf` and returns
   best-effort extracted profile fields. Must never overwrite user data destructively.
5. **Reset.** `make reset` backs up user data to `.reset-backup/<ts>/` and re-inits an empty
   DB. It **preserves** `.env` and `portals.yml`. (This is why a post-reset machine can have
   a saved LLM key but `provider: none`.)

**Keep multi-party product concepts out of this repo.** Consent gates, referral
claims, and candidate PII sharing belong in private platform code — not here.

6. **Background jobs never auto-submit.** `make scheduler`, `make ingest` and
   `make jobs-sweep` only discover, refresh and archive.

---

## Coding rules (and landmines)

**Data contract (from [AGENTS.md](AGENTS.md) — do not break):**
- Never overwrite the **user layer**: `cv.md`, `config/profile.yml`, `modes/_profile.md`,
  `portals.yml`, `data/*`, `reports/*`, `output/*`, `interview-prep/*`.
- Personalization goes in `config/profile.yml` / `modes/_profile.md`, never `modes/_shared.md`.
- **Other people's data does not belong in this repo.** Keep candidate résumés and
  referral history out of git. Confidential JD imports (if any) stay gitignored.

**Store / migrations:**
- Migrations are a version ladder in `store/db.py::_run_migrations`. SQLite has no
  `ADD COLUMN IF NOT EXISTS`, so column additions go through
  `_add_column_if_missing()`, not the `.sql` file — a half-applied migration must
  re-run safely.
- **`jobs.status` is unusable as a lifecycle flag** — `upsert_job` overwrites it on
  every re-scrape. The v7 lifecycle columns (`archived_at`, `last_checked_at`,
  `liveness`, `dead_strikes`) are deliberately **absent from `upsert_job`'s SQL** so a
  re-scrape can never resurrect an archived job. Keep them out of it.
- **Timestamps compared in SQL must use SQLite's format** (`%Y-%m-%d %H:%M:%S`), not
  `isoformat()`. `'T' > ' '`, so a mixed-format string comparison silently never
  matches — this is what made the liveness recheck window never open.
- Upserts are batched (`upsert_jobs`, `add_jobs_to_pipeline`): one connection for the
  whole list. The per-row path re-ran the entire migration ladder on every job.
- Deleting a job means deleting its `pipeline` rows first (`pipeline.job_id REFERENCES
 jobs(id)` with `PRAGMA foreign_keys = ON`). `purge_archived` does this; ad-hoc SQL
 cleanup that forgets it leaves orphans — `make verify` catches them.
- **A `worker_queue` row in `running` is a claim, not progress.** Only the worker that
 claimed it moves it off, and the worker is a **daemon thread** — Python kills those
 outright on process exit, so no `finally` runs. `make api` runs under `--reload`, so a
 saved file restarts the server; a scan takes 2.5–8.5 min, so the window is wide. A
 stranded `discover` blocks both `enqueue_task` (which dedupes against it and returns the
 dead row's id, so the UI reports success) and `_claim_pending` (which cancels new ones
 while it sits there). Since v18 a live worker writes `heartbeat_at` every
 `HEARTBEAT_SECONDS`, and `reap_stale_tasks()` frees anything silent for
 `HEARTBEAT_STALE_SECONDS`; `STALE_TASK_MINUTES` is only the fallback for rows with no
 heartbeat. **If you add a task type, run it inside `_heartbeating()`** or it will be
 reaped mid-run. Call the reaper before reading queue state, not after.
- `GET /jobs?status=all` falls through to a catch-all query that does **not** join
  `pipeline`. For candidate matching use `store/queries.fetch_candidate_jobs()`, never
  that path.

**Ingestion / cron:**
- `make ingest` calls the discovery orchestrator **directly**, never
  `scan_scheduler.scan_is_due()` — that helper's 120s boot grace returns False forever
  while `last_scan_at` is NULL, so a one-shot cron would never fire its first scan.
- `sources/fetcher.DEFAULT_TTL` is 7200s, exactly the 2h cron cadence. Ingest forces
  `ttl=3300` so alternate ticks don't serve a cached snapshot.
- Overlapping ticks are skipped via `flock` on `data/.ingest.lock`.
- The liveness sweep archives only on the **second consecutive** dead verdict; 403s and
  timeouts are `uncertain` and never count. Purge is 30 days *and* unreferenced.

**LLM:**
- "Available" requires **both** a provider (`profile.yml → llm.provider`, not `none`)
  **and** a key (`.env → SHORTLISTR_LLM_API_KEY`). A key alone is not enough.
- **Grok ≠ Groq.** `grok` is xAI (keys `xai-`, api.x.ai); `groq` is groq.com Llama
  inference (keys `gsk_`, api.groq.com). Both reuse the OpenAI-compatible client.
  Key prefixes are auto-detected in `profile_store._detect_provider_from_key`.
- Every LLM call has a deterministic fallback (heuristic eval, unranked matches,
  original resume). A provider outage must degrade, never break a flow.
- Secrets only via `secrets_store` / `.env` — never `profile.yml`, never a URL.

**Frontend:**
- Use the design tokens — `lime`, `sage`, `mist`, `ink`, `stone`, `orange` — not raw Tailwind
  palette colors. See [docs/UI_DESIGN_STANDARDS.md](docs/UI_DESIGN_STANDARDS.md).
- `tsc --noEmit` must stay clean. API client types live in `dashboard/src/lib/api/client.ts`;
  keep them in sync with backend responses.

**Process:**
- Branch off `main`; don't commit straight to `main`. Commit/push only when the user asks.
- Run `make test` + `npx tsc --noEmit` before every commit.
- Minimal diffs. One focused task per change.
- **No CLI after first install.** Once `make start` has succeeded, day-to-day
  setup belongs in the dashboard — especially Connections (Playwright install,
  LLM key, platform passwords). Do not add or leave user-facing hints that say
  `make install` / `playwright install` / edit `.env` by hand when a UI path
  exists. Doctor/toast copy should point at Connections.
- `make api` now really does run with `--reload` (the Makefile exports
  `SHORTLISTR_API_RELOAD=1`; reload is opt-in inside `api/main.py`). A request mid-restart
  can return a transient 500 — retry before treating it as a bug. **If live behavior
  contradicts green tests, check which code the server process is actually running
  before touching the algorithm.**
- Current baseline: **900 tests pass, 0 fail.** Keep it that way. An older generation of
  failures came from reading the live `config/profile.yml` instead of pinning their own
  targeting; they hid a real bug where saving a profile retargeted discovery but not scoring.
- **`tests/test_discover_flow.py::test_progressive_persist_writes_after_each_source` is
  flaky (~1 run in 3).** It passes in isolation and fails only in a full run.
  `discover_and_filter()` ends with `enrich_thin_matching_jobs()` and
  `verify_pending_gmail_stubs()`, both of which touch the real network — the suite logs
  live `HTTP 429`s. Re-run before believing a failure there, and don't "fix" the
  persistence logic on its say-so.
- **Verify a push landed.** `git push origin main` while checked out on another
  branch pushes the *local* `main` ref, which may not have moved — five verified
  fixes once sat unpushed that way while every command reported success. Check
  `git rev-parse HEAD` against `origin/main` after pushing, not the exit code.
- **Module-level paths are computed at import.** Several modules snapshot a
  directory or a config value when they load, so setting the matching env var
  inside a test does nothing once that module is imported. This has produced a
  vacuously-passing test and a test that wrote into live data. If a test needs a
  different directory, patch the module attribute, not just the environment.
- **`deal_breakers` match the title AND the JD body; `exclude_titles` match the
  title only.** Never put a role word in `deal_breakers`. On a real inbox,
  "manager" appeared in 27 of 161 postings and in only 6 titles, so filtering
  management roles that way would have binned 21 genuine engineering jobs for
  saying "you will report to the engineering manager".
- **`target_titles` are substring matches**, so `"Site Reliability Engineer"`
  already covers Senior/Staff/Principal. Listing those separately is dead config,
  and it hides how narrow the list really is. It is also the first gate in
  discovery — an unlisted title is dropped before it is scored, so this one value
  decides most of what the user ever sees.
- **Don't ask an LLM for a holistic score and expect a spread.** Scores clustered
  at 4.2/4.5/4.8 across 158 jobs and were uncorrelated with fit — jobs rated <40
  by discovery averaged *higher* than jobs rated 60-79. Adding rubric bands
  changed almost nothing. What worked was making the model enumerate the
  posting's hard requirements, mark each met/unmet with evidence, and score from
  that list. Ground the number in something countable.
- **A failing free backend must back off.** DuckDuckGo answers a bot challenge in
  ~12s, and one prep bundle makes six searches — 72 of 76 seconds spent waiting
  on six guaranteed failures. Anything on a free tier that can refuse should be
  asked once, then skipped for a cooldown.
- **Don't assume a filter's rejection rate is a bug, or that it isn't.** A 99.4%
  drop rate looked like over-filtering; checking whether eval scores tracked
  discovery fit is what proved the score was uninformative. Check the correlation
  before rewriting the filter.

---

## Memory loop (retrieve → generate → store)

Project memory lives in [docs/memory/](docs/memory/) as plain markdown so any session
(or model) can read it.

- **Retrieve:** at session start, skim [docs/memory/decisions.md](docs/memory/decisions.md)
  (durable facts/decisions) and [docs/memory/incidents.md](docs/memory/incidents.md)
  (past bugs + root causes) for anything touching today's task.
- **Generate:** fold the relevant items into your plan/spec before coding.
- **Store:** after a meaningful fix/decision, append an entry (what changed, why, tests,
  key logs). Only durable things — see the hygiene rules in
  [docs/memory/README.md](docs/memory/README.md).

---

## Common commands

```bash
make start            # first run: install deps, seed files, start stack, open /onboarding
make install          # Python deps + Playwright Chromium
make dashboard-install # dashboard npm deps
make api              # backend API (uvicorn, 127.0.0.1:8787, reload on)
make dashboard-dev    # Next.js dashboard (localhost:3000)
make scheduler        # background discovery scanner
make test             # python test suite (pytest over tests/)
python3 -m pytest tests/test_discovery.py -q       # single test file (from repo root)
python3 -m pytest tests/test_discovery.py -q -k name  # single test by name
make reset            # blank-slate reset (backs up user data, keeps .env/portals.yml)
make uninstall        # remove Shortlistr (keychain/crons/build); then delete the folder
                      # ARGS=--purge-data also wipes résumé/profile/DB/.env
cd dashboard && npx tsc --noEmit   # frontend type check
cd dashboard && npx next lint      # frontend lint
```


Other CLI entry points (all `python -m automation.cli <cmd>`, wrapped by make): `doctor`,
`verify`, `scan`, `evaluate`, `status`, `tracker`, `apply-assist`, `seed`. See the
[Makefile](Makefile).
