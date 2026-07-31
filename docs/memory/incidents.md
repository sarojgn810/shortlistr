# Incidents & RCAs (episodic memory)

Bugs and surprising behavior, with root cause and fix, so we don't relearn them. Newest
first. Keep logs short — quote the key lines, don't paste megabytes.

Template:
```
## YYYY-MM-DD — <symptom>
**Symptom:** what was observed.
**Root cause:** the actual reason.
**Fix:** what changed (files).
**Guard:** the test/check that now prevents regression.
```

---

## 2026-07-31 — Résumé prep showed "2 changes" of nonsense
**Symptom:** Job detail / Prep showed `Résumé prep (2 changes)` with a unified
diff of `+# Applying for: …` or, after LaTeX CV gen, 100+ lines of TeX source.
**Root cause:** `prep.diff` invented a header that is not in the real PDF, and
`record_tailored_artifact` stored `.tex` under `tailored_html_path`, which the
diff then "stripped as HTML" against `cv.md`.
**Fix:** Honest readiness summary (same baseline content; PDF ready or not);
store `.tex` as `tailored_tex_path`; UI shows summary + bullets, not raw diffs.
**Guard:** `tests/test_j1.py::test_diff_reports_same_baseline`,
`::test_diff_ignores_legacy_tex_as_html`.

## 2026-07-31 — LinkedIn optimizer showed another laptop's target role
**Symptom:** After setting a different `config/profile.yml` on a second machine,
LinkedIn still defaulted to Site Reliability / the previous person's draft.
**Root cause:** (1) Hardcoded `target_role="sre"` defaults in API/UI blocked
auto-detect when a role string was present. (2) `data/linkedin_optimizer.json`
draft (gitignored but often copied with the folder) was loaded without checking
it belonged to the current candidate.
**Fix:** Derive default role from live profile titles (`role_from_profile` /
`detect_role_id`); treat missing/blank role as auto; stamp drafts with
`owner` (email/name) and ignore stale drafts; stop forcing `"sre"` in the
client import URL helper.
**Guard:** `tests/test_linkedin_optimizer.py::test_role_from_profile_titles`,
`::test_stale_linkedin_draft_ignored`.

## 2026-07-30 — LinkedIn/Naukri jobs offered a "Prefill form" button
**Symptom:** Postings discovered from LinkedIn and Naukri showed the form-apply
UI (Prefill form / Fill form) on Apply, the job detail modal and Prep, even
though those pages are login-walled ads with no fillable application form.
**Root cause:** `apply_channel_for()` classified *any* job with a URL as
`"form"` — it only distinguished email (has `company_email`) from manual (no
URL). Board host was never considered.
**Fix:** New `automation/apply/channels.py` (`is_link_only`, `NotFillableError`)
listing aggregator/login-walled hosts; `apply_channel_for()` returns a new
`"link"` channel for them; `apply_assist_for_job()` refuses link-only postings
before launching a browser (422 from the endpoint); Apply / JobDetailModal /
PrepDetailPanel show "Open posting" only, and the prep bundle now carries
`apply_channel`.
**Guard:** `tests/test_batch_apply.py::test_job_board_listings_are_link_only`
and `::test_apply_assist_refuses_link_only_posting`.

## 2026-07-30 — Job cards showed 6.0/5 and blamed a missing résumé
**Symptom:** Discover cards showed impossible scores like `6.0/5`, repeated
`title match; title match (no résumé skills to compare)` even with a full
`cv.md`, and LinkedIn guest rows with empty JDs outscored enriched ones.
**Root cause:** (1) UI mapped `fit_score/10` onto a /5 badge without clamping,
while fit can reach 60–90. (2) Scorer took the empty-JD branch whenever
`skills and jd` was falsy, and that branch re-appended "title match" while
blaming the résumé. (3) `skill_signals()` split category blobs
(`SRE & Reliability SLO…`) so almost nothing substring-matched a real JD.
**Fix:** Clamp card/row/modal display at 5.0; honest reasons
(`JD not fetched yet` / `résumé skills not parsed yet`); mine atomic tech
tokens from the résumé for overlap; clamp stored fit at 100.
**Guard:** `tests/test_job_card_scoring.py`.

**Symptom:** Recent runs discovered ~3,900 jobs and passed ~29; Settings showed
thousands saved while on-target yield stayed near zero. Live audit:
watchlist_ats 3505→15 (0.4%), aggregators 131→5, Naukri/search/Ashby 0.
**Root cause:** Three silent source failures plus the wrong search shape.
1. Ashby GraphQL still queried removed fields (`isRemote`, `externalLink`); the
   API answered HTTP 200 with `errors`, so every board looked empty.
2. Naukri public search returned `406 recaptcha required` and was logged at
   debug, then treated as "no results".
3. DuckDuckGo HTML search returned HTTP 202 anomaly pages; `raise_for_status`
   does not fail on 202, so all queries "succeeded" with zero cards.
4. Separately, watchlist ATS downloads whole company boards (mostly EU/US
   titles) instead of searching by keyword+location for India.
**Fix:** Correct Ashby query; raise/surface Naukri CAPTCHA and DDG challenges
via `FetchStats.error` + circuit failure; add free LinkedIn guest search for
title×location; expand India-verified ATS boards only.
**Guard:** `tests/test_source_failures.py`, `tests/test_linkedin_guest.py`,
`automation/tools/source_audit.py`.

## 2026-07-30 — A dead worker wedged Scan permanently; button span for a day
**Symptom:** The Discover "Scan job boards" button had been spinning since the
previous evening. `GET /jobs/discover/status` returned `running: true` with a
`worker_queue` row claimed at `2026-07-29 19:07:32` and never finished. Clicking
Scan again did nothing at all.
**Root cause:** `_claim_pending` sets a row to `running`, and nothing except the
worker that claimed it ever moves it off. Killing/restarting the API mid-scan
stranded the row, and a stranded discover blocks the feature twice over:
`enqueue_task` dedupes by returning any pending/running discover's id, so every
later click was answered with the dead row and never queued; and `_claim_pending`
cancels new pending discovers while one is "running". There was no timeout — the
wedge was permanent.
**Fix:** `worker_queue.started_at` (schema v15) records claim time.
`store.db.reap_stale_tasks()` fails anything `running` past
`STALE_TASK_MINUTES` (30). Called from `enqueue_task`, `_claim_pending`, and
`/jobs/discover/status` — so simply opening Discover unsticks it even with no
worker alive. `COALESCE(started_at, created_at)` covers rows from before the
column, and the comparison stays in SQLite's datetime format.
**Guard:** `tests/test_stale_worker_tasks.py`.

## 2026-07-30 — Résumé preview iframe warned it could escape its sandbox
**Symptom:** Console filled with "An iframe which has both allow-scripts and
allow-same-origin for its sandbox attribute can escape its sandboxing"
(`about:srcdoc`), once per preview render.
**Root cause:** `CvHtmlPreview` set `sandbox="allow-scripts allow-same-origin"`.
That pair lets the framed document reach its own sandbox attribute and clear it,
so the sandbox is decorative — which is exactly what Chrome flags.
**Fix:** `sandbox="allow-scripts"`. The only script in the preview is the
one-page fit routine, which measures and scales its own DOM; it never touches the
parent, storage or the network, so same-origin bought nothing.
**Guard:** none automated — one attribute, covered by the comment at the call
site.

## 2026-07-30 — "31 pending review" badge was a page length, not a count
**Symptom:** TopBar showed "31 pending review". The number happened to be right
(31 targeted pending jobs), but was computed by filtering the first page of
`/jobs?status=inbox` (LIMIT 100). Today also showed `jobs.length` as "New jobs
to review", counting evaluated and approved rows too. The apply runner built its
queue by filtering a page of "evaluated" for approved ones.
**Root cause:** Headline counts were derived from paginated list responses.
**Fix:** Badge and Today cards read `pipeline_targeted` from `/pipeline/stats`
(SQL COUNT behind the same relevance + fit gate). Apply runner asks for
`status=approved` directly. TopBar refreshes its own count on every page.
**Guard:** `tests/test_pending_count.py`.

## 2026-07-30 — Long Education titles were justified; two degrees merged
**Symptom:** After the LaTeX rebuild, an Executive PhD title spanning two lines
came out with rivers of white space, and the B.Tech rendered as the PhD's
institution in the small italic used for employers.
**Root cause:** `\cvsplit` cancelled `\rightskip` to make `\hfill` work, which
re-justified the title when it wrapped. Separately, `expect_meta` treated the
next date-bearing line as a subtitle after an entry was promoted from prose.
**Fix:** Measure the date box first, set the title ragged-right in the remaining
width. A date-bearing follow-on line is another entry, not meta.
**Guard:** `tests/test_cv_reflow.py` (two degrees / subtitle / skills label).

## 2026-07-30 — Deleting profile.yml left the previous targeting alive
**Symptom:** `reload_discovery_config()` returned early when the profile file was
missing, so `SEARCH_KEYWORDS` kept whatever the process had loaded at import —
a first-run API that imported against a leftover profile never fell back to the
field-neutral defaults.
**Root cause:** Early return on missing file; empty `target_titles` also left the
previous list untouched.
**Fix:** Missing or empty profile resets to `_DEFAULT_SEARCH_KEYWORDS` and
`["remote"]`.
**Guard:** `tests/test_first_run_e2e.py::test_empty_profile_falls_back_to_generic_titles`.

## 2026-07-30 — Résumé PDFs ran to four pages of broken bullets
**Symptom:** Generating any LaTeX template against the user's `cv.md` produced a
3–4 page PDF where every experience bullet was its own one-item list and the
wrapped remainder sat underneath as an orphan paragraph. Dates did not flush
right consistently. The HTML "single page · auto-fitted" preview clipped the
overflow instead of saying so.
**Root cause:** `cv.md` came from PDF ingest and is hard-wrapped (~130 chars/line).
Both `_md_to_latex_body` and `_md_block_to_html` treated each source line as a
paragraph. Separately, eleven of twelve `.tex` templates were self-titling stubs
without `\entry` / Projects / Additional, and page "fit" was an HTML scale+clip.
**Fix:** Shared `cv/reflow.py` rejoins wrapped bullets and prose; all 12 templates
rebuilt on `cv/latex_layout.py`; `fit_to_pages` measures real page count and walks
a density ladder; dashboard shows the compiled PDF; apply-time uses LaTeX too.
**Guard:** `tests/test_cv_reflow.py`, `tests/test_cv_page_fit.py`.

## 2026-07-30 — Apify "no token" test made live API calls
**Symptom:** `test_apify_adapter_skips_without_token` passed in the sandbox but
failed with network on, returning 84 jobs and spending Apify credits.
**Root cause:** The adapter does `from sources.apify_client import get_apify_token`
at import time. Patching `apify_client.get_apify_token` left the adapter's own
binding pointing at the real function.
**Fix:** Patch `sources.adapters.apify_adapter.get_apify_token` instead.
**Guard:** same test, with a comment explaining the binding.

## 2026-07-29 — React: two children with the same key `AI Operations Engineer`
**Symptom:** Profile page threw "Encountered two children with the same key,
`AI Operations Engineer`" (twice) in the Next.js overlay.
**Root cause:** `target_titles` had a hand-saved duplicate, and the profile chips
keyed React children by the title string (`key={t}`). Same latent risk for
preferred locations and skill chips.
**Fix:** `_parse_titles` / `get_profile_for_ui` dedupe case-insensitively on save
and read; profile chips use `key={`${t}-${i}`}`; `dedupe_skills` on job/tracker
list APIs so skill chips can't collide either.
**Guard:** `tests/test_unique_list_values.py`.

## 2026-07-29 — "Continue Setup" still on Today after setup is done
**Symptom:** Today/home showed a Continue Setup CTA despite a filled profile,
real résumé, LLM key, and thousands of jobs in the DB.
**Root cause:** the banner keyed only off `automation.onboarding_complete`, a
sticky flag set solely by the onboarding wizard's Done step. Completing setup
via /profile + /cv upload never flips it (and this machine had no `automation`
row in `user_settings` at all).
**Fix:** `/setup/status` now reports `onboarding_complete` when the wizard flag
is set **or** essentials are met (name+email+target titles, non-placeholder
`cv.md`, sqlite). Incomplete setups get `onboarding_gaps` so the banner names
what is actually missing.
**Guard:** `tests/test_onboarding_complete.py`.

## 2026-07-29 — Evaluating a job erased its source, salary and fit score
**Symptom:** found while verifying the MLOps fix — 30 Apify-discovered jobs had
`source='eval'`, `fit_score=0` and no location or salary, and were missing from
candidate matching.
**Root cause:** `eval/service.py` upserts a placeholder `JobRecord(source="eval", …)`
to attach a result for a pasted URL. `_UPSERT_JOB_SQL` guarded company/title/jd_text
against blanks but assigned `location`, `salary`, `fit_score`, `fit_reason` and `source`
unconditionally — so evaluating a discovered job overwrote all of them, and
`queries.NO_EVAL_ARTIFACTS` ("AND j.source != 'eval'") then filtered the job out.
**Fix:** those columns keep their existing value when the incoming record is blank
(score 0 counts as blank — it means "this writer didn't score"), and `'eval'` never
replaces a real discovery source. A re-scrape with better data still wins.
**Guard:** `tests/test_upsert_preserves_discovery.py`. Existing rows were repaired
in place (source recovered from `notes`, re-scored with `score_job`).

## 2026-07-29 — MLOps/AIOps in the profile, but only SRE jobs discovered
**Symptom:** profile targeted SRE + MLOps + AIOps; the inbox was all SRE. MLOps/AIOps
titles that *were* already in the DB (e.g. "Senior ML Ops Engineer, AI Platform Team")
sat tagged `off_target`.
**Root cause:** three separate things, each enough on its own.
1. The profile said `MOps Engineer` — a typo, so MLOps was never a keyword at all.
2. `passes_title_location` matches keywords literally, so the single spelling
   "MLOps Engineer" missed "ML Ops", "Machine Learning Operations", "AIOps Specialist".
3. Every source took `SEARCH_KEYWORDS[:5]` (Apify, Naukri) or `[:4]` (search), and the
   list opened with four SRE seniority variants — so the searches were 100% SRE. Apify's
   `max_pairs: 1` credit guard then reduced that to one query, repeated on all 7 boards.
   `LOCATION_KEYWORDS` also fed "bangalore" *and* "bengaluru" as separate paid searches.
**Fix:** `config._TITLE_FAMILIES` expands each targeted title into the spellings boards
use (kept tight — bare "machine learning" would flood the inbox with research roles);
`search_titles()` picks one term per family before any seniority variant;
`search_locations()` collapses city spellings; Apify offsets each board into the pair
pool so `max_pairs: 1` still covers SRE + MLOps + AIOps per scan at the same credit cost.
Callers: `apify_adapter`, `naukri_scraper`, `search_discovery`, `remoteok_scraper`.
**Guard:** `tests/test_title_families.py` — board spellings pass, adjacent ML research
roles still drop, `search_titles(3)` covers all three families, boards rotate families.

## 2026-07-29 — Three pipeline dead ends (approve / submit / re-evaluate)
**Symptom:** "Could not approve" on a fresh inbox card; a submitted job that had once
been skipped disappeared from the tracker board; Re-evaluate did nothing on skipped jobs.
**Root cause:** All three asked the state machine for an illegal single hop.
`pending → approved`, `evaluated → submitted` and `skipped → evaluated` are not edges in
`PIPELINE_TRANSITIONS`; the callers either raised (approve, re-evaluate) or silently
skipped the pipeline update while still writing `applications.status='applied'`, and
`fetch_tracker_board` filters `p.status = 'skipped'` out — so the row vanished.
**Fix:** `_walk_pipeline_to()` steps through the required intermediate states
(`pending → evaluated → approved → submitted`, `skipped → pending → …`) instead of
hopping; `mark_evaluated` revives skipped jobs; `mark_skipped` is idempotent. The ladder
itself is unchanged — the user's decision is honoured, the bookkeeping catches up.
**Guard:** `tests/test_j1.py::test_approve_straight_from_inbox`,
`test_submit_a_previously_skipped_job`, `test_reevaluating_a_skipped_job_revives_it`.

## 2026-07-29 — Discover page appeared to reload every few seconds
**Symptom:** during a scan the whole Discover page flashed to skeletons every 3s; scroll
position, filters and selection were disorienting.
**Root cause:** the poll loop called `fetchJobs()` without the `background` flag, so
`setIsLoading(true)` ran on every tick and `setJobs(fresh)` replaced the array wholesale,
remounting every row/card.
**Fix:** poll the new cheap `GET /jobs/discover/status`, refresh with `background=true`,
and merge by id reusing unchanged objects (`mergeJobs`) so React keeps existing rows
mounted; new arrivals surface as a "+N new jobs" pill. Polling stops when the queue
reports the scan finished, and re-attaches to a scan already running.
**Guard:** `tests/test_discover_flow.py` (queue dedupe + claim + progressive persist).

## 2026-07-29 — Discover looked empty while multi-board Apify scan ran
**Symptom:** "Scan job boards" returned 200 / enqueued; inbox stayed empty for minutes.
**Root cause:** Async discover finished *all* sources (8 Apify boards × up to 180s each,
plus Greenhouse/Lever/…) before the first `persist_discovered`. UI only polled ~60s.
Worker held the SQLite connection open for the whole scrape; a second click stacked
another full discover.
**Fix:** Persist after each source (`persist_progressively=True`); claim/release queue
rows around work + dedupe pending discovers; cap Apify per-board timeouts when many
boards are enabled; poll Discover UI for up to ~6 minutes with `isDiscovering` held.
**Guard:** worker no longer wraps long `discover_and_filter` inside one `store.db()`;
`enqueue_task("discover")` returns existing pending/running id.

## 2026-06-30 — Dashboard scan button caused socket hang up
**Symptom:** clicking "Scan job boards" → browser console shows `ECONNRESET` / 500.
API logs show `Failed to proxy … socket hang up`.
**Root cause:** sync `/jobs/discover` blocks for 60-150s+ (Naukri 15 pairs × 2.5s sleep +
DuckDuckGo timeouts). Next.js proxy drops connections after ~60s.
**Fix:** frontend sends `async_run=true`; backend enqueues + spawns immediate worker
thread; frontend polls for results every 3s.
**Guard:** endpoint returns instantly (enqueued response); worker processes in background.

## 2026-06-30 — Discovery scan took 150s+ and returned 0 search results
**Symptom:** `make start` logs showed every DuckDuckGo query timing out at 15s each.
Total scan blocked for 150s+, causing Next.js proxy `ECONNRESET` on the sync endpoint.
**Root cause:** DuckDuckGo HTML scraping is blocked/rate-limited. 10+ queries × 15s
timeout with no circuit breaker or total cap.
**Fix:** `FETCH_TIMEOUT` 15→8s, 30s total time cap, 2-consecutive-failure circuit breaker
in `discover_from_search()`. Port cleanup in `start-local.sh`.
**Guard:** circuit breaker logs warnings; search completes in <35s even when fully down.

## 2026-06-30 — Auto-eval spammed 25 noisy warnings per scan with no LLM
**Symptom:** scheduler logs filled with `Auto-eval <id>: ...` warnings and UNIQUE
constraint violations every scan cycle.
**Root cause:** auto-eval loop ran unconditionally even when `llm.provider: none`.
**Fix:** added LLM availability guard before the eval loop in `scan_scheduler.py`.
**Guard:** `logger.info("Auto-eval skipped: no LLM configured")` when provider is none.

## 2026-06-30 — Remote aggregator jobs flooding city-only user inbox
**Symptom:** user with `preferred_locations: [Bengaluru, Bangalore, Bhubaneswar]` saw
"Remote" jobs from RemoteOK/Himalayas/Remotive in inbox.
**Root cause:** `filter.py` unconditionally skipped location checks for remote sources.
**Fix:** added `WANTS_REMOTE` flag; bypass only when user has remote terms in locations.
**Guard:** `tests/test_location_targeting.py` — 4 tests for both paths.

## 2026-06-30 — ~99% of discovered jobs were non-actionable (invalid id)
**Symptom:** clicking a job (view/evaluate/approve/skip) failed for nearly all
inbox jobs; `GET /jobs/<id>` → `400 Invalid job_id format`. 939/3313 DB rows had
non-hex ids (RemoteOK numeric, WeWorkRemotely guid=URL, NoDesk/Jobspresso href).
**Root cause:** `JobRecord.__post_init__` only hashed the URL when `job_id` was
empty, so source-provided ids became the DB primary key, which fails the API's
`^[a-f0-9]{16}$` `validate_job_id`.
**Fix:** `JobRecord.__post_init__` now ALWAYS sets `job_id = job_id_from_url(url)`
(source id kept in `metadata.source_job_id`). One-time migration
`automation/store/migrate_job_ids.py` (`make`/CLI `migrate-job-ids`) rewrote 939
rows across jobs+pipeline+applications+eval_results+receipts (FK enforcement off +
`foreign_key_check` before commit). Verified RemoteOK/WWR jobs now do
detail→evaluate→approve→skip→undo all 200.
**Guard:** `tests/test_job_id_canonical.py` (5 tests). Migration is idempotent.

## 2026-06-30 — First-run lands on a populated, untargeted dashboard
**Symptom:** a blank install (no profile/CV) opens `/dashboard` already full of
generic "WORLDWIDE" jobs; onboarding is only a secondary card, so users start in
Discover and get untargeted results that (pre-id-fix) didn't even open.
**Root cause:** `/` always redirects to `/dashboard`; no first-run gate.
**Fix:** `dashboard/app/dashboard/page.tsx` redirects to `/onboarding` when
`status.checks.profile === false`; onboarding step chips past step 0 are locked
until a profile is saved.
**Guard:** browser-verified redirect; manual (no unit test for client routing).

## 2026-06-30 — LLM setup check stays unchecked despite a saved key
**Symptom:** onboarding "Local setup checklist" shows LLM unchecked; `/setup/status`
returns `api_key_set: true` but `provider: "none"`, `available: false`.
**Root cause:** not a bug — a state. `make reset` wiped `config/profile.yml` (provider →
`none`) but preserved `.env` (key survived). LLM "available" needs **both** a provider
and a key.
**Fix:** added a hint in the onboarding LLM section when a key is saved but provider is
`none`. Resolution for the user: pick a provider and save (key already present).
**Guard:** documented in [decisions.md](decisions.md) (local-first/reset) + CLAUDE.md
critical flows.

## 2026-06-30 — `POST /jobs/discover` returned 500
**Symptom:** browser console `api/jobs/discover … 500` during active development.
**Root cause:** transient — `make api` runs uvicorn with `--reload`; editing backend
files restarts the server, and a request mid-restart 500s. Both discover paths return
200 once the reload settles.
**Fix:** none needed. Documented as a known gotcha in CLAUDE.md/WORKFLOW.md ("retry a
500 right after a backend edit").

## 2026-06-30 — "Hyderabad only" search still returned every metro
**Symptom:** setting preferred location to one city still matched all Indian metros.
**Root cause:** `region: india` injected a fixed metro list into `LOCATION_KEYWORDS`, and
preferred locations were *added* to it; the filter passes a job if **any** keyword matches.
**Fix:** preferred locations are now authoritative — they replace the metro default
(`automation/config.py`, both code paths).
**Guard:** `tests/test_location_targeting.py` (Hyderabad → `['hyderabad']`; blank → metro
fallback; preferred + remote keeps remote, drops metros).

## 2026-06-30 — Pipeline page showed "100 pending" and empty downstream columns
**Symptom:** Pipeline badge/columns wrong; approved/submitted jobs missing.
**Root cause (two):** (1) the page used `useJobs("all")` → catch-all query without
`pipeline_status`, so everything looked pending. (2) the tracker board used
`LIMIT 200 ORDER BY added_at DESC`, pushing the few approved/submitted rows (added early)
past the limit.
**Fix:** Pipeline reads `/tracker/board`; tracker board orders non-review statuses first.
**Guard:** verified live (Review/Approved/Applied/Active show real counts). Tracker board
fix is in `automation/api/tracker_board.py`.

## 2026-06-30 — skip → un-skip → submit blocked
**Symptom:** `400 Cannot transition application 'skip' → 'applied'` after reconsidering a
skipped job.
**Root cause:** `skip` was terminal in `APPLICATION_TRANSITIONS`.
**Fix:** `skip → {evaluated, applied}` allowed.
**Guard:** `tests/test_j1.py::test_skip_then_reconsider_then_submit`.

## 2026-07-25 — Testbed served stale code: `make api` had no reload
**Symptom:** after fixing the engage matcher, the testbed still returned old role
cards ("Here are your best-matching open roles" + no city/why lines). Tests passed;
direct function calls returned the new output; the live API did not.
**Root cause (two independent bugs):**
1. `make api` never enabled reload. `api/main.py` gates it behind
   `SHORTLISTR_API_RELOAD` (opt-in), so the process served whatever code it imported
   at boot — for hours. CLAUDE.md claimed `make api` runs with `--reload`; it did not.
2. `engage_sessions.data.matches` cached the role list forever. Any non-pick message
   replayed the frozen list, so even fresh code would show old cards to a returning
   candidate — and could point at a req that has since closed.
**Fix:** Makefile `api` target exports `SHORTLISTR_API_RELOAD=1`; `_cached_matches()`
reuses cards only when fresh (15 min TTL) AND current-schema, else recomputes.
**Lesson:** when live behavior contradicts green tests, verify WHICH code the server
process is running before touching the algorithm again.

## 2026-07-29 — Resume upload left discovery on starter titles
**Symptom:** after uploading an SRE resume, scans still surfaced broad roles like product,
marketing, and analyst jobs; many inbox rows were marked relevant but had `fit_score=0`.
**Root cause:** `/cv/upload` extracted profile hints but never persisted `target_titles`
or reloaded discovery config. The starter profile titles in `config/profile.yml`
(`Software Engineer`, `Data Analyst`, `Product Manager`) kept driving
`SEARCH_KEYWORDS`, and the default inbox hid only `off_target` rows, not low-fit ones.
**Fix:** resume upload now persists extracted titles back into the profile, reloads
discovery config immediately, and returns the applied titles. Title extraction now
collects multiple experience roles plus conservative aliases. Default inbox queries
also require `fit_score >= min_fit_score` unless the caller asks for `relevance=all`.
**Guard:** `tests/test_profile_extract.py`, `tests/test_cv_upload.py`,
`tests/test_pre_dogfood.py`.

## 2026-07-29 — Off-target jobs still visible: the gate covered one read path
**Symptom:** after resume-targeted discovery shipped, Discover correctly showed 3
matching SRE roles, but Pipeline → Review listed ~200 jobs including Account
Executive and Management Accountant, and Today's "Evaluated, ready to review"
card read 79. The user reported still seeing jobs that were supposed to be gone.

**Root cause:** three read paths onto the same pipeline, one gate.
`api/jobs_api.fetch_jobs` filtered on relevance + fit;
`api/tracker_board.fetch_tracker_board` and `store/status.pipeline_status_counts`
did not. The board and the headline counts re-exposed everything the inbox had
filtered out, so the filter looked broken from the UI even though it worked.

Two further defects surfaced while fixing it:
- **`or 40` swallowed a configured 0.** `int(getattr(_cfg, "MIN_FIT_SCORE", 40) or 40)`
  turned a deliberate `min_fit_score: 0` ("show me everything") back into 40. A
  truthiness check cannot distinguish "unset" from "zero" for a numeric setting.
- **Three tests read the live `config/profile.yml`.** `test_fetch_jobs_enriched`,
  `test_fetch_jobs_resolve_optional` and `test_fetch_evaluated_jobs` created
  unscored fixtures and broke as soon as the real profile had a non-zero
  threshold — the same unpinned-targeting failure as 2026-07-28.

**Fix:** the SQL predicates moved to `store/queries.py` (`RELEVANT_ONLY`,
`MIN_FIT_ONLY`, `NO_EVAL_ARTIFACTS`, `APPROVED_ONLY`, `min_fit_threshold()`) so
every read path shares one definition. The board and `pipeline_status_counts`
now apply it, both with an `all` escape hatch (`/tracker/board?relevance=all`,
plus a Relevant/All toggle on Pipeline mirroring Discover). Jobs the user already
approved, submitted or applied to bypass the gate — a retarget must never make an
in-flight application disappear.

**Guard:** `tests/test_http_fixtures.py` —
`test_tracker_board_review_hides_off_target`,
`test_pipeline_counts_targeted_vs_raw`, `test_min_fit_threshold_respects_zero`.

**Lesson:** a filter is a property of the data, not of the query that happens to
implement it. When the same rows are readable from more than one endpoint, the
predicate belongs in one shared place — otherwise the newest read path silently
reverts the filter, and the UI, not the tests, is what tells you.

## 2026-07-25 — Fusion defects: the platform leaking into the local tool
Found by mapping the (A) local-tool / (B) platform boundary after both had grown
in one process. Four real defects, all introduced by (B) landing inside (A):

1. **One-sided moderation gate.** `store/queries.fetch_candidate_jobs` filtered
   `review_status` but `api/jobs_api.fetch_jobs` did not, and
   `intake.store_attested_openings` called `add_jobs_to_pipeline` unconditionally.
   A stranger's chat submission was hidden from candidates yet appeared in the
   OWNER's Discover inbox and was queued for auto-evaluation — the exact inverse of
   the intent. Fix: `_APPROVED_ONLY` on every `fetch_jobs` branch; pipeline insert
   moved to `jobs/review.py` on approval.
2. **`set_status` became unreachable code.** Inserting `companies_for`/`inbox`
   above it in `referrals/registry.py` consumed its `def` line; the body sat after
   `inbox()`'s return. Tests stayed green because nothing called it — a reminder
   that "tests pass" says nothing about code no test exercises.
3. **Auth fell through to anonymous OWNER** when `SHORTLISTR_JWT_SECRET` was set
   without `SHORTLISTR_API_TOKEN` — configuring auth made the API look protected while
   granting everyone full access. Now fails closed with 401.
4. **Forced first scan.** `_start_background_scheduler` set `should_run = True` on
   the first tick, so a fresh clone ran a full multi-portal scan ~5s after boot
   against the seeded sample profile, before onboarding. Now honours `scan_is_due()`.

Also fixed: `_show_matches` sent candidates to `awaiting_resume` when inventory was
empty — a dead end whose only prompt asked for the resume they had just sent (what
every fresh clone hit).

**Lesson:** when a multi-party subsystem lands inside a single-user app, every
read path needs auditing, not just the one you added. The gate you write protects
the query you were thinking about; the leak is in the query you weren't.
