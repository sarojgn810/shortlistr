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

## 2026-08-08 — Casing is not evidence of a technology (the fix for "AWS" broke Pune)
**Symptom:** #15 stopped `AWS` being read as the candidate's home city by
rejecting all-caps tokens up to six characters. That rule was wrong in both
directions, and neither direction had a test that could see it.
**Root cause:** casing was being used as the place-vs-technology signal, and it
is not one.
  - **False negatives.** `PUNE`, `DELHI`, `DUBAI`, `LONDON`, `BERLIN` are four
    to six characters and are set in caps whenever the contact row is.
    `_single_token_location('PUNE')` returned `True` before #15 and `False`
    after. The consequence is bigger than a blank field: no `location` means
    `preferred_locations` is never seeded, `config.LOCATION_PREFERENCE_SET`
    evaluates `False`, and `pipeline/filter.py:83` then short-circuits
    `passes_title_location` to `True` for **every** posting — the geo filter
    silently stops filtering.
  - **False positives.** The rule missed anything longer or title-case, so the
    original bug was still live one token up: `_extract_location` still returned
    `Terraform`, `KUBERNETES`, `JENKINS` and `AWS GCP Azure` as places.
    `looks_like_location` (`linkedin_optimizer/parser.py`) accepts any 2–30 char
    alphabetic part with no role word, so it cannot be the backstop here.
**Fix (#16, `cv/profile_extract.py`):** `_NOT_A_PLACE_TECH` names the
technologies. A segment is rejected when *every* word in it is one —
whole-segment, so a PDF-flattened skills row is caught while a city sharing a
word with the list is not. Tokens that are also real places (Phoenix, Berlin,
Austin, Cordoba) are deliberately excluded; `java`, `oracle`, `apache` are kept.
The all-caps rule survives capped at **three** characters as the generic catch
for unknown acronyms (ETL, RCA, OOP), and a segment carrying a slash is never a
place — which is what `CI/CD` needed all along.
**Two more from the same review, same file:**
  - `_ADJACENT_ROLES` was matched in **dict insertion order** and broke on the
    first hit, so `MLOps Platform Engineer` matched `platform engineer` before
    `mlops` was tested and got the SRE family with no ML family at all. Since
    `target_titles` is the first discovery gate and is substring-matched, that
    profile could only ever see a posting titled "MLOps Platform Engineer". The
    family now follows where the *title* puts each trigger, ties to the longer.
  - Title dedupe compared exact strings, so caps headings put both
    `DEVOPS ENGINEER` and `DevOps Engineer` in the profile — duplicates in the
    onboarding UI, and slots spent against the 16-title cap. Dedupe is
    case-insensitive now, with `_CANONICAL_TITLES` choosing the spelling.
**Not fixed:** `Data Infrastructure Engineer` still misses the Data/Analytics
family. That is not an ordering problem — `"data engineer"` is not a substring
of it. A broader `"data "` trigger would also catch `Data Center Engineer`, so
widening the first discovery gate on that guess was not worth it.
**Guard:** four tests in `tests/test_onboarding_targeting.py`, each failing
against the previous code —
`test_longer_technology_names_are_not_read_as_a_home_city`,
`test_an_all_caps_contact_row_still_yields_its_city` (unit + end-to-end),
`test_the_title_picks_its_family_not_the_dict_order`,
`test_a_caps_heading_is_not_a_second_target_title`. 1059 tests pass.
**Lesson worth keeping:** #15's own tests passed because every fixture was
title-case (`Bangalore`, `London`). A heuristic that reads a *styling* property
of the input needs fixtures in the other styling — otherwise the test only
re-states the assumption. This is the second time in this file a green suite
described the bug rather than caught it.

---

## 2026-08-02 — Aggregators and LinkedIn guest, the last two slow sources
**Symptom:** With Workday and Gmail dealt with, `aggregators` (14.6s) and
`linkedin_guest` (17.7s) were most of a 42s scan.
**Root cause — different for each, and the difference matters:**
  - **aggregators** was the Workday shape again: a sequential loop over seven
    independent boards. WorkingNomads alone took 7.5s to return **1** job; five of
    the seven cost 13.5s between them for 4 jobs, while RemoteOK and Remotive
    delivered 134 in 2.5s.
  - **linkedin_guest** was *not* the same. It is 10 searches against a single
    host, each followed by a deliberate 0.8–1.4s pace, with 429/Retry-After
    handling. Roughly 11s of the 17.7s is that pacing, and it is correct —
    parallelising it would be rude and risks a block.
**Fix:** aggregators go through `parallel_call` (seven different hosts, so no
extra load on any one). LinkedIn keeps its pacing and gets a disk cache instead:
`read_cached_text` / `write_cached_text` in `sources/fetcher`, keyed on the
search params. `_request_page` now returns `(html, from_cache)` and the caller
**skips the sleep on a hit** — otherwise a fully cached run would still spend the
whole delay budget having sent nothing. A non-200 is never cached, so a 429 can
never be kept alive for the TTL.
**Result:** aggregators 16.0s → 7.0s (bounded by WorkingNomads), same 138 jobs.
LinkedIn 17.7s → 0.0s cached, identical 60 listings. Full scan 42s → 18s.
Across all the scan work: **356s → 18s**.
**Also fixed:** the existing LinkedIn tests wrote fixture HTML into the *real*
`data/cache` once guest search started reading it, so one test's cached page
satisfied the next test's request (the 429 test stopped seeing its 429), and a
live scan could have ingested "Acme India" as a real listing. `tests/
test_linkedin_guest.py` now has an autouse fixture pointing `fetcher.CACHE_DIR`
at tmp_path.
**Guard:** `tests/test_aggregators_parallel.py` (boards overlap, one dead board
does not empty the source, raw_count matches records) and the caching tests in
`tests/test_linkedin_guest.py` (a cached search sends nothing and sleeps not at
all; a blocked response is never cached).

---

## 2026-08-02 — Gmail spent 42s per scan to return nothing
**Symptom:** Once Workday was cached, `gmail` became the largest source in a
scan: 42.5s, 0 raw jobs, every time.
**Root cause:** Two things, and the "0 jobs" was not the bug. Of 100 listed
messages, 42 were already ingested and skipped, leaving **58 downloaded in full,
sequentially, on every scan**:
  - 27 were not job alerts at all. The query was `newer_than:7d` with no sender
    filter, so the whole mailbox came back and `is_alert` was evaluated *after*
    downloading each full message — a round-trip per message purely to read its
    `From` header.
  - 31 were alert mail with genuinely no job link ("verify your address",
    "questionnaire pending", digests that are all social buttons). Those ids were
    deliberately *not* remembered, per a comment fearing a decode bug would
    permanently bury unread digests — so they were re-fetched forever.
Returning 0 records was correct: the 42 messages that did carry jobs had already
been ingested. Extraction itself was fine — the hirist digests still yield 12
real job URLs including SRE roles.
**Fix:** `_alert_sender_query()` moves the sender filter into Gmail's `q`
(`newer_than:7d (from:… OR …)`), and messages checked-but-empty are recorded in
`empty_ids`, guarded by `EXTRACTOR_VERSION`. Bumping that constant re-examines
every remembered-empty message, which honours the original concern instead of
overriding it: a regex or decode fix cannot bury a digest.
**Result:** 42.5s every run → 26.6s first run (populating `empty_ids`) → **0.9s
steady state**, 47x. Full scan 81s → 42s. It also *recovered* jobs: the
unfiltered query spent 27 of its 100-message budget on non-alert mail, crowding
out real alerts, so the first filtered run surfaced **12 job records** the old
path never saw.
**Guard:** `tests/test_email_monitor.py` — the query filters by sender, an empty
sender list degrades to the plain query, a link-less message is remembered, a
remembered one is not re-fetched, bumping `EXTRACTOR_VERSION` re-examines it, and
already-ingested ids are still skipped.

---

## 2026-08-02 — The ingest TTL override never did anything
**Symptom:** Found while adding POST caching for Workday. `jobs/ingest.py` lowers
the cache window with `fetcher.DEFAULT_TTL = 3300` (and restores it after), so
alternate 2h cron ticks cannot serve the same cached snapshot — the comment says
so explicitly. It had no effect.
**Root cause:** `cached_get_json(..., ttl: int = DEFAULT_TTL, ...)`. A default
argument is evaluated **once, at import**, so the parameter was permanently bound
to 7200. Reassigning the module attribute afterwards changed the module global
but never the bound default, and no caller passed `ttl` explicitly — so every
ingest ran with exactly the window it was trying to avoid. This is the
import-time landmine already called out in CLAUDE.md, in library code rather than
a test.
**Fix:** `ttl: int | None = None`, resolved through `_resolve_ttl()` at call time.
**Guard:** `tests/test_fetcher_cache.py` — `_resolve_ttl` follows a reassigned
`DEFAULT_TTL`, an explicit ttl still wins, and lowering the module attribute makes
an already-cached entry stale on the next call.

---

## 2026-08-02 — Workday paid full latency on every re-scan (no cache)
**Symptom:** After parallelising, Workday still cost ~35s on every scan, even
when re-scanning minutes later with nothing changed.
**Root cause:** Workday's CXS endpoint only answers POST, and the shared cache
(`sources/fetcher.cached_get_json`) was GET-only, so `workday_scraper` used raw
`requests.post` and cached nothing — unlike Greenhouse/Lever, which have been
cached all along.
**Fix:** Added `cached_post_json`, sharing the same disk cache and retry path
(both now factored into `_read_cache`/`_write_cache`/`_fetch_with_retries`). The
cache key is url + the payload canonicalised with `sort_keys=True`. That detail
is the whole correctness story: Workday pages a board by posting a different
`offset` to the *same* URL, so keying on the URL alone would serve page 1's
postings for pages 2 and 3 and a board would look like the same 20 jobs three
times.
**Result:** Workday 35.1s cold → 0.1s warm (513x), identical job set both runs.
Full scan 89s → 81s — a small end-to-end gain because Workday stopped being the
bottleneck. With it cached, the remaining cost is **gmail at 42.5s for 0 raw
jobs**, then linkedin_guest 17.7s and aggregators 14.6s. Gmail is the next lever.
**Guard:** `tests/test_fetcher_cache.py` — offsets 0/20/40 must produce three
cache entries, key is stable across dict ordering, a non-200 is never cached
(caching a 500 would hide a board for the whole TTL), and a truncated cache file
falls back to the network instead of raising.

---

## 2026-08-02 — Workday was 97% of every scan
**Symptom:** A full discovery scan took ~6 minutes. Per-source stats showed
`workday` at 232s against `watchlist_ats` at 2.5s — and watchlist_ats returned
9,765 raw postings to Workday's 771.
**Root cause:** `fetch_workday_raw()` was a plain for-loop over 15 boards, each
walking up to 3 pages, one request at a time. Timing each board individually:
five tenants (Zillow, Red Hat, CrowdStrike, Palo Alto, Pluralsight) answered in
~34s each while the other ten took 1–8s — for the *same* 60 postings. So the cost
was not volume, it was waiting on a handful of slow hosts in series. The
codebase already had `sources/parallel.parallel_flat_map` and the cached async
fetcher, and `watchlist_ats_adapter` used them; Workday used raw `requests.post`
and neither.
**Fix:** `fetch_workday_raw()` now maps boards through `parallel_flat_map`
(max_workers=10). Every board is a different myworkdayjobs tenant, so overlapping
them adds no load on any single host — each worker talks to a different server.
Pagination *inside* a board stays sequential: offsets are walked in order and the
loop breaks on a short page. The import is function-local because
`sources/__init__` builds the registry, which imports the Workday adapter, which
imports this module.
**Result:** Workday 216s → 35.2s (6.1x), bounded now by the slowest single board.
Full end-to-end scan 356s → 89s (4x).
**Guard:** `tests/test_workday_portals.py` — a fake `_scrape_company` that sleeps
asserts overlap actually happens (peak in-flight > 1, wall clock well under
sequential), and one failing board must not lose the others.

---

## 2026-08-02 — Scans strand for 30 minutes after any API restart
**Symptom:** "make api is taking much time" — really: after some scans, clicking Scan did
nothing at all for half an hour, with no error. `worker_queue` showed discover tasks
`failed` after 1801s and 1908s, against 151–521s for ones that actually worked. 3 of the
last 6 discovers failed this way.
**Root cause:** The scan runs in a `daemon=True` thread (`api/main.py` — the scheduler
loop and the `discover-immediate` dispatch). Python kills daemon threads outright when
the process exits: no `finally`, no `except`, so `_finish()` never runs and the claim is
never released. `make api` sets `SHORTLISTR_API_RELOAD=1`, so **every saved file under
`automation/` restarts the server**, and a scan takes 2.5–8.5 minutes — during
development the odds of killing one in flight are high. The row then sat `running`, where
it blocked scanning twice over: `enqueue_task` dedupes against
`status IN ('pending','running')` and returned the *dead row's id*, so the endpoint
answered `{"enqueued": <dead id>}` — a success the UI believed — while `_claim_pending`
refused to start anything new. `reap_stale_tasks` only freed rows older than
`STALE_TASK_MINUTES = 30`, which is why the failures clocked ~1800s: that was not work,
it was waiting for the timer. The 30-minute reaper had been added earlier for this exact
symptom, but it treated the clock as a proxy for "is the owner alive", so the root cause
survived.
**Reproduced:** claim a task in a child process, `kill` it, observe the row stay `running`
while `enqueue_task` returns the dead id and `_claim_pending` returns `[]`.
**Fix:** v18 adds `worker_queue.owner` and `worker_queue.heartbeat_at`. A live worker
beats every `HEARTBEAT_SECONDS` (15) from `_heartbeating()` in `workers/discovery_worker.py`;
`reap_stale_tasks` frees any `running` row silent for `HEARTBEAT_STALE_SECONDS` (90).
Silence is a real liveness signal — the beat thread dies with the process, which is the
point. Rows with no heartbeat still fall back to the 30-minute check, so the change can
only reap more than before, never less. Chose a heartbeat over storing a pid because pids
get recycled and `os.kill(pid, 0)` is not a liveness probe on Windows, which CI runs.
Dead zone: 30 min → ~90s.
**Guard:** `tests/test_stale_worker_tasks.py` — a silent worker is reaped without the
timeout, a *beating* worker is never reaped even when older than `STALE_TASK_MINUTES`,
claiming stamps owner + first beat, the heartbeat refuses to touch a non-`running` row,
and end-to-end the next Scan gets a new id and actually runs.

---

## 2026-08-01 — Groq 404 on leftover Ollama model tag (re-hit)
**Symptom:** Eval toast `AI helper unavailable … model qwen2.5:0.5b does not exist`
while provider is Groq.
**Root cause:** Local AI model id left in `profile.yml` / stale `GroqProvider`
cache after switching to Groq; coerce existed on save/build but did not persist
or self-heal a live provider instance.
**Fix:** Persist coerced model to profile; `llm_status` force-reloads on mismatch;
`GroqProvider.complete` swaps Ollama-style ids (and retries on `model_not_found`);
Connections save strips Ollama tags for cloud providers.
**Guard:** `test_build_cloud_persists_coerced_groq_model`,
`test_groq_complete_swaps_ollama_tag`.

---

**Symptom:** `ApiError: Internal Server Error` on `/jobs`; Discover count jumps
empty ↔ full. Same on a brand-new laptop install.
**Root cause:** No SQLite busy timeout / WAL; `init_db()` re-ran migrations on
every `db()` open; API + scheduler raced on first boot; frontend cleared the
job list on any 500.
**Fix:** `busy_timeout=30s` + WAL; process cache + cross-process migrate flock;
list_jobs retries lock once (503); Discover keeps existing rows on transient
errors.
**Guard:** `tests/test_db_concurrency.py::test_connect_enables_wal_and_busy_timeout`.

## 2026-08-01 — Chat 404 on Groq with Ollama model tag
**Symptom:** Assistant “status” returned `model_not_found: qwen2.5:0.5b` on Groq.
**Root cause:** Local AI wrote an Ollama tag into `profile.yml`; switching to
`provider: groq` left the model untouched; chat surface raw LLM exceptions.
**Fix:** `coerce_cloud_model()` on save + `_build_cloud`; chat `except` →
`_fallback()`; Connections clears Ollama tags when picking Groq.
**Guard:** `tests/test_demo_hardening.py::test_coerce_cloud_model_drops_ollama_tags`,
`tests/test_agent_chat.py::test_chat_llm_error_falls_back_to_commands`.

## 2026-07-31 — Prep page showed another laptop's proof points
**Symptom:** Prep guides / CV PDF / skills on Prep belonged to a different
person after copying the project folder between machines.
**Root cause:** `_latest_prep_path` matched `interview-prep/*Company*` (and
could fall back to any file); `find_cv_pdf` fell back to the newest PDF in
`output/` when the company slug missed.
**Fix:** Prep files are `{job_id}.md` with `owner` + `job_id` front matter;
load only owned guides; CV PDFs prefer `job_id` in the filename and never
return an unrelated PDF when a company filter is set. Fit score (eval /5 or
discovery /100) is passed through and shown on Prep.
**Guard:** `tests/test_prep_ownership.py`.

## 2026-07-31 — Resume HTML preview looked oversized and clipped long CVs
**Symptom:** Template / Quick preview showed huge type and cut off lengthy
resumes instead of flowing onto page 2.
**Root cause:** Preview drew a fixed `210mm` A4 sheet inside a ~520px iframe
(unscaled), and `single_page=True` + `overflow:hidden` shrunk/clipped instead
of paginating.
**Fix:** Viewport-width sheets + relative type; default multi-page when content
won't fit at a readable size; iframe grows with reported page count; Length
"1 page" still tries to tighten first.
**Guard:** `tests/test_cv_preview.py::test_render_prefers_multi_page_by_default`.

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

## 2026-08-01 — Interview prep is company-researched, not a static clone
**Decision:** Prep guides research the company interview process + role questions
via Serper (when keyed), merge JD-derived prompts, optionally draft STAR answers
with the configured LLM from live `cv.md`, and fall back to a short *labeled*
practice bank only when research is empty. Unstamped legacy `interview-prep/`
files are never loaded (stops copied personal Q&A on a new laptop).
**Why:** Every job used the same SRE question bank; folder copies leaked another
person's guides.
**Touches:** `prep/research.py`, `generate_prep.py`, `prep/ownership.py`,
PrepDetailPanel, `tests/test_prep_research.py`.

## 2026-08-01 — LinkedIn TARGET ROLE still defaulted to Site Reliability
**Symptom:** Fresh onboarding / new-laptop profile showed Site Reliability /
Platform pre-selected in LinkedIn TARGET ROLE.
**Root cause:** `role_from_profile()` fell through to discovery
`SEARCH_KEYWORDS` then hardcoded `fallback="sre"`; empty/generic titles never
matched a pack so every blank profile became SRE. Draft `target_role` was also
honored even when the draft profile was empty.
**Fix:** Derive role only from real `profile.yml` `target_titles`; unmatched →
`""`; UI placeholder “Choose a target role…”; ignore draft role until the draft
profile is substantial.
**Guard:** `tests/test_linkedin_optimizer.py::test_role_from_profile_empty_never_defaults_to_sre`.

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

## 2026-07-30 — Discover scanned thousands of jobs but almost none were good
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
**Fix:** none needed. Documented as a known gotcha in CLAUDE.md/CLAUDE.md ("retry a
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
