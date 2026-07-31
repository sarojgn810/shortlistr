# Decisions (semantic memory)

Durable facts and decisions about how Shortlistr works and **why**. Newest first.
One decision per entry. If a decision is reversed, edit the entry and note the date.

Template:
```
## YYYY-MM-DD — <short title>
**Decision:** what we decided.
**Why:** the reasoning / what it prevents.
**Touches:** files or areas.
```

---

## 2026-07-31 — Shortlistr résumé templates + Resume page UX
**Decision:** Keep the 12 single-column LaTeX skins (IDs unchanged for
settings continuity) but rebrand display names to **Shortlistr …** (Classic,
Professional, Compact, Campus, Crimson, Teal, Serif, Executive, Skills, Air,
Split, Plain). Catalogue lists `recommended` + `inspiration` (Jake/sb2nov,
Awesome-CV, Reactive-Resume, latexcv). Resume `/cv` gains upload, clearer
Generate PDF CTA, and a template gallery with Recommended badges.
**Why:** Users saw weak/ambiguous template names and a Resume page that told
them to upload elsewhere. PDF truth remains LaTeX; HTML preview stays approximate.
**Touches:** `automation/cv/templates.py`, `latex_layout.py`, `templates/cv-latex/`,
`dashboard/.../CvWorkspace.tsx`, `app/cv/page.tsx`, client `CvTemplate` type.

## 2026-07-31 — Chat agent uses profile + shared Telegram front-end
**Decision:** Inject a compact profile/CV snapshot into `agent.chat` system
prompt (`agent/user_context.py`). Expand tools with `shortlistr.whoami`,
`shortlistr.skip`, `shortlistr.prep`. Telegram stays a thin front-end on the same
`chat()` core: persist `chat_id` + short history in `data/telegram_bot.json`,
expose `notify` / `notify_job`, and ping the phone when the agent evaluates a
job ≥ 3.5/5 (best-effort; requires `make telegram` running). Never auto-submit.
**Why:** Chat previously knew tools but not the candidate; Telegram had no
memory or outbound path and overclaimed “approve/skip prompts.”
**Touches:** `automation/agent/{chat,registry,dispatch,user_context}.py`,
`connectors/telegram.py`, Connections Telegram copy, tests.

## 2026-07-30 — Writing quality layer (not detector evasion)
**Decision:** Add `automation/writing/` (policy, sanitize, style prompts,
self_check) and wire it per call site for cover letters, LinkedIn
rewrites/polish, eval A–G *block strings*, interview prep, chat *answer*
text, fit reasons (label mode), recruiter reply drafts, and
`modes/_shared.md`. Do **not** wrap `LLMProvider.complete()` globally —
that would corrupt eval JSON and chat tool-call JSON.
**Why:** Generated copy was accumulating banned fluff and throat-clearing even
in offline templates. Named pattern cleanup makes drafts more concrete without
claiming watermark stripping, classifier defeat, or “no AI traces.”
**Touches:** `automation/writing/`, cover_letter, linkedin_optimizer/rewriter,
eval/service + prompts, generate_prep, agent/chat, job_filter, email_monitor,
eval/explain, modes/_shared.md, `tests/test_writing_quality.py`.

---

## 2026-07-30 — LinkedIn Profile Optimizer is copy-only + heuristic-first
**Decision:** Ship a LinkedIn Profile Optimizer workspace (single sidebar
“LinkedIn” item + in-page tabs at `/linkedin`) that imports from résumé or
LinkedIn URL/paste, scores against role packs, and rewrites sections grounded
in evidence only. Changes are copy/paste into LinkedIn — never auto-edit the
network. Public LinkedIn URL fetch is best-effort and often login-walled; CV
import is the reliable ground truth. Rewrites must not invent employers,
metrics, or unproven keywords (those stay as optional recommendations).
**Why:** Recruiter discoverability is a first-class job-search asset alongside
the résumé, but LinkedIn automation is brittle and against product ethics.
Hallucinated “optimizations” destroy trust.
**Touches:** `automation/linkedin_optimizer/`, `api/linkedin_optimizer.py`,
`dashboard/app/linkedin/`, `dashboard/src/components/linkedin/`,
`tests/test_linkedin_optimizer.py`.
**Updated:** 2026-07-30 — collapsed noisy sidebar group; CV/URL import gate;
grounded rewriter.

## 2026-07-30 — User DB is profile-scoped (persist gate + retarget purge)
**Decision:** Discovery only upserts jobs that pass title/location *and* the
fit floor (`jobs_for_user_db`). Off-target and low-fit rows never inflate the
user DB. On profile targeting change, `retag_existing_jobs` re-scores keepers
and **purges** mismatches, except pipeline `approved`/`submitted` and
application `applied`/`responded`/`interview`/`offer`/`rejected` (those are
re-tagged `off_target` but kept). Scan stats expose `persist_gate`
(fetched/kept/dropped_*).
**Why:** Warehousing every board hit then UI-filtering made Discover look empty
while Settings reported thousands of saved jobs. The product promise is
relevant matches, not a scrapyard.
**Touches:** `orchestrator/discovery.py`, `jobs/ingest.py`,
`scheduler/scan_scheduler.py`, `api/main.py` `/jobs/discover`,
`tests/test_persist_gate.py`, `tests/test_retag_targeting.py`.

## 2026-07-30 — Steal page compression, not a scraper framework
**Decision:** Do not depend on or name third-party “LLM scrape graph” libraries.
Steal only: (1) HTML→markdown compression that mines `__NEXT_DATA__` / inline
JSON before stripping scripts, (2) requests-first page fetch with Playwright
fallback for empty SPA shells. Wire dead `scan_method: websearch` portal rows
into `load_search_queries` (capped). Post-persist JD enrich fills thin
LinkedIn/search rows. No free proxies, CAPTCHA bypass, or auto-submit.
**Why:** Discovery yield is already limited by silent zeros and empty JDs, not
by missing anti-bot infra. Compression improves local-LLM/eval token cost and
fit scoring; websearch portal wiring unlocks config that was never read.
**Touches:** `portals_config.get_websearch_company_queries`,
`processors/search_discovery.py`, `scrapers/html_text.py`,
`scrapers/browser_fetch.py`, `processors/enrich_jd.py`,
`ats_url_resolver._resolve_careers_html`, tests.

## 2026-07-30 — Free LinkedIn guest search is a first-class source
**Decision:** Discovery includes a `linkedin_guest` adapter that hits LinkedIn's
signed-out public listings endpoint (`jobs-guest/.../search`). It needs no login,
cookies, or Easy Apply; it never submits. Query pairs come from
`search_titles()` × (`search_locations()` + remote-in-country when the profile
wants remote). Requests are paced and 429s are retried once, then surfaced as a
source error. Apify LinkedIn remains optional paid coverage.
**Why:** Local scrapers were company-list crawlers (Greenhouse/Lever) or blocked
(Naukri CAPTCHA, DuckDuckGo 202). Nothing free did keyword+location search for
India. Live probe: ~141 unique guest cards → ~47 on-target (33% hit) vs
watchlist_ats 0.4%.
**Touches:** `scrapers/linkedin_guest.py`, `sources/adapters/linkedin_guest_adapter.py`,
`sources/registry.py`, `config.py`, `profile.example.yml`,
`tests/test_linkedin_guest.py`.

## 2026-07-30 — Source `FetchStats.error` is a failure, not a silent zero
**Decision:** When an adapter returns with `stats.error` set, discovery calls
`record_failure` and logs a warning even if the call itself did not raise.
Naukri CAPTCHA (HTTP 406), DuckDuckGo anomaly/202, Ashby GraphQL schema errors,
and LinkedIn guest 429 after retry all set that field. A source that returns
`raw=0` with no error is still allowed (empty board / no matches).
**Why:** Three sources were returning zero forever while looking healthy —
Ashby returned GraphQL errors under HTTP 200; Naukri 406 and DDG 202 never raised.
**Touches:** `orchestrator/discovery.py`, `scrapers/ashby_scraper.py`,
`scrapers/naukri_scraper.py`, `processors/search_discovery.py`,
`tests/test_source_failures.py`.

## 2026-07-30 — India ATS watchlist prefers verified public boards
**Decision:** Expand `portals.yml` / `portals.example.yml` only with boards that
responded live today (Greenhouse/Lever/Ashby). Prefer India-heavy employers
(HackerRank, Thoughtworks, Navi, Meesho Lever, PhonePe/Razorpay/…) and platforms
with real Bangalore/Remote-India openings (Elastic, MongoDB, Databricks, Stripe,
Twilio). Upgrade websearch-only entries to their public API when found. Do not
add boards with zero India locations just because the API is up.
**Why:** Watchlist volume without India relevance recreates the 0.4% hit-rate
problem. LinkedIn guest covers keyword search; ATS watchlist should cover
employers that actually hire here.
**Touches:** `portals.yml`, `templates/portals.example.yml`.

## 2026-07-30 — Apify belongs in Connections / first-run setup
**Decision:** Apify is no longer docs-only. Connections has a “More job boards”
card (token + enable toggle + $5 free-credit guide). Welcome/setup checklist
recommends it. Enabling adds `apify` to `sources.enabled` with default boards
naukri/linkedin/indeed and `max_pairs: 1`. Still optional for `ready`, but
recommended for coverage.
**Why:** Free $5 Apify credit is enough for personal searches; keeping it only
in `profile.yml` / `.env` violated the no-CLI-after-install rule and hid the
highest-coverage source from non-technical users.
**Touches:** `connections_store.py`, Connections page, WelcomeOverview,
SetupChecksCard, `/setup/status`, `tests/test_connections.py`.

## 2026-07-30 — Local AI shows hardware fit + guided install
**Decision:** Connections Local AI surfaces a capability report (RAM, CPU, OS
tier), ranks catalog models as smooth/tight/heavy, pre-selects the best fit,
and shows a step-by-step guide before download. Silent auto-pull is opt-in via
``SHORTLISTR_LOCAL_AI_AUTOSTART=1``; default is user-confirmed Install.
**Why:** Non-tech users need to see what their machine can run, not get a
surprise multi-hundred-MB download of a model that may thrash 8 GB RAM.
**Touches:** `llm/hardware.py`, `llm/local_ai.py`, Connections UI.

## 2026-07-30 — Local AI auto-bootstrap for non-technical first run
**Decision:** New installs default to ``llm.provider: auto``. On API start (and via
Connections → Set up Local AI) we best-effort install/start Ollama, pull
``qwen2.5:0.5b``, and stamp profile to ``auto``. ``get_llm`` resolves
**Local AI → cloud key (if present) → heuristic**. Cloud providers with an
explicit choice are never overwritten. Windows may still need a one-time
Ollama.app install; Mac/Linux try brew/install.sh.
**Why:** Non-tech users should not paste API keys or run terminal pulls to get
better-than-basic scoring; tiny local models fit ~8 GB RAM laptops.
**Touches:** `llm/local_ai.py`, `llm/__init__.py` (`auto`), Connections UI,
`/setup/local-ai/*`, profile defaults.

## 2026-07-30 — No-LLM is a first-class mode (basic scoring)
**Decision:** Auto-eval no longer skips when `llm.provider` is `none` — it runs
`evaluate_job_text`, which falls back to a CV/JD-overlap heuristic that fills
all A–G blocks. Inbox bulk re-evaluate is unlocked without an AI key. Cover
letter templates pull proof points from `cv.md`, not a fixed SRE `SKILL_MAP`.
Chat offline fallback names Connections and supports pipeline/prep commands.
`features.tool_calling` mirrors `available` (the chat tool-loop).
**Why:** Discover → approve → prep → apply already worked offline; auto-eval
and bulk re-eval were the last hard gates that made “no key” feel broken.
**Touches:** `scan_scheduler.auto_evaluate_pending`, `eval/service._heuristic_eval`,
`cover_letter`, `agent/chat._fallback`, inbox page, `llm/status.py`.

## 2026-07-30 — Prep is a first-class sidebar page
**Decision:** Application prep (cover letter + interview guide + tailored CV for
one company) lives under **Work → Prep**. The index is a card grid of approved /
submitted roles; clicking a card opens a modal with the full pack. Deep links
`/prep?job={id}` and `/prep/{id}` still work. Listing is `GET /prep`.
**Why:** Prep was only reachable via Pipeline approve → generate, with `/prep`
redirecting away — hard to revisit materials before applying.
**Touches:** `api/prep_bundle.list_prep_summaries`, Prep page + modal,
sidebar nav, `PrepDetailPanel`.

## 2026-07-30 — Settings is plain-language too (no CLI / no scheduler terminal)
**Decision:** Settings matches Connections UX: optional intro, collapsible sections,
friendly labels (“Find new jobs automatically”, “How picky should scoring be?”),
expandable help, Save buttons. Removed the Local-dev terminal block and any
`make scheduler` / `make api` copy — the API already runs the background scan.
AI keys stay linked out to Connections.
**Why:** Same non-technical user as Connections; Settings was still speaking in
dev-tooling terms.
**Touches:** `dashboard/app/settings/page.tsx`, `AutomationPanel.tsx`.

## 2026-07-30 — Connections is for non-technical users (no jargon / no CLI)
**Decision:** The Connections page is the only place a general user configures
email, AI, LinkedIn/Naukri, Playwright, and Telegram. Copy is plain language
(“Send email”, “App Password”, expandable how-to). Secrets save with a button;
Gmail inbound is Upload JSON → Connect Gmail (browser opens) — never
`make setup-gmail` or hand-placing files. MCP stays collapsed under Advanced.
**Why:** Asking non-technical users for env vars or Cloud Console paths loses them.
**Touches:** Connections page, `connections_store`, `/setup/gmail/*`, decisions
on no-CLI-after-first-install.

## 2026-07-30 — No CLI after first install; Connections is the fix surface
**Decision:** After the user has run `make start` once, they must never be told
to open a terminal for day-to-day setup. Missing Playwright/Chromium is fixed
with **Connections → Install Playwright** (`POST /setup/playwright/install`),
which installs the pip package if needed and then downloads Chromium. LLM keys,
platform passwords, Gmail app password, Telegram token, and MCP servers are
edited and saved on the same page. Toasts and doctor hints point at Connections,
not `make install` / `playwright install`.
**Why:** A local-first tool that still dumps users into the shell after onboarding
feels unfinished. The first install is the only intentional CLI moment.
**Touches:** `connections_store.install_playwright_chromium`, Connections page,
`SetupChecksCard`, apply-assist error toasts, `doctor.check_playwright` fix text.

## 2026-07-30 — Headline counts come from SQL, not from a page of rows
**Decision:** Any number shown next to a list (`N pending review`, Today's
"New jobs to review", "Active conversations", the apply runner's queue length)
is a `COUNT(*)` behind the same relevance + fit gate as that list
(`pipeline_status_counts(targeted=True)` / `application_status_counts`), never
a `.filter(...).length` over `listJobs` / `/applications`. The apply runner
asks `GET /jobs?status=approved` rather than filtering an "evaluated" page.
**Why:** List endpoints are LIMITed (100 / 200). Deriving a total from them
caps silently and, for the inbox, counted evaluated and approved rows as
"new to review".
**Touches:** `store/status.py`, `/pipeline/stats`, `useApiStatus`, TopBar,
Today, `apply/page.tsx`, `jobs_api` `status=approved`.

## 2026-07-30 — LaTeX-first résumé templates with measured page fit
**Decision:** Every résumé template is a single-column LaTeX skin over one shared
preamble (`cv/latex_layout.py`): ligatures off, hyphenation off, widows/clubs
forbidden, `\cvsplit` for flush-right dates (because `\raggedright` eats `\hfill`),
`\entry`/`\cvsection` macros, A4. Hard-wrapped PDF-ingest markdown is rejoined
in `cv/reflow.py` (shared by LaTeX + HTML) so bullets stop becoming one-item
lists with orphan continuations. Page length is a measured promise: `fit_to_pages`
compiles, counts pages with pypdf, and walks a density ladder until the target
(`auto` / 1 / 2) is met — nothing is clipped. Apply-time PDFs use the same LaTeX
pipeline. The dashboard shows the compiled PDF by default; the HTML preview is
labelled as approximate.
**Why:** Eleven of twelve templates were self-titling stubs that dropped Projects/
Additional, the HTML "fit to one page" script clipped overflow, and apply-assist
attached a different renderer than Regenerate. The user's `cv.md` (hard-wrapped
from PDF ingest) rendered as four pages of broken bullets.
**Touches:** `templates/cv-latex/*.tex`, `cv/latex_layout.py`, `cv/reflow.py`,
`cv/latex_builder.py`, `cv/preview.py`, `processors/generate_cv.py`,
`CvWorkspace.tsx`, `CvPdfPreview.tsx`, doctor, tests.

## 2026-07-30 — Application Auto-Fill fields + live Chromium fill
**Decision:** Expand `application:` in profile with work authorization, preferred
name, cover-letter snippet, and willing-to-relocate (alongside the existing
website / notice / CTC / how-heard). Apply-assist matches them by label heuristics
and never submits. `reload_discovery_config()` also refreshes `CANDIDATE` +
`APPLICATION` so a Profile save is live without restart. Profile save preserves
hand-edited `sources` / `discovery` / `mcp_servers`. `file://` fixtures are allowed
for local Chromium verification.
**Why:** ATS forms ask these constantly; previously only five answers were editable
and a save left apply-assist on stale import-time globals. EEO (gender/disability)
stays manual — too sensitive to auto-fill.
**Touches:** `config.py`, `profile_store.py`, `apply/ats_fill.py`, Profile +
onboarding UI, `profile.example.yml`, `tests/test_application_autofill.py`.

## 2026-07-29 — Targeting works in role families, not raw keyword order
**Decision:** A profile title is expanded into its family's spellings
(`config._TITLE_FAMILIES`: MLOps ↔ ML Ops ↔ Machine Learning Operations, AIOps ↔
AI Ops ↔ AI Operations, SRE ↔ Site Reliability, …) so the discovery filter
recognises whatever spelling a board uses. Sources that can only afford a few
searches call `config.search_titles(n)` / `search_locations(n)`, which return one
term per role family and one term per city instead of `SEARCH_KEYWORDS[:n]`.
Apify additionally offsets each board into the title×location pool, so
`max_pairs: 1` covers every family across a scan at unchanged credit cost.
**Why:** Titles are listed seniority-variant-first ("Site Reliability Engineer",
"SRE", "Principal…", "Senior…"), so a `[:5]` slice searched one role and ignored
the rest of the profile — the user's MLOps/AIOps targets were never queried, and
MLOps postings already in the DB were tagged `off_target`. Families stay narrow
on purpose: bare "machine learning" would pull in ML research roles, which is the
blast-radius problem this repo exists to avoid.
**Touches:** `config.py`, `sources/adapters/apify_adapter.py`,
`scrapers/naukri_scraper.py`, `scrapers/remoteok_scraper.py`,
`processors/search_discovery.py`, `tests/test_title_families.py`.

## 2026-07-29 — Apify multi-board registry + job-card enrichment
**Decision:** Expand opt-in Apify behind a board registry (LinkedIn, Naukri,
Naukrigulf, Indeed, Dice, Monster, Seek, Upwork, HN Who’s Hiring, plus optional
Glassdoor/ZipRecruiter). Greenhouse/Lever/Ashby stay on free local
`watchlist_ats`; Remotive/Himalayas/RemoteOK stay on aggregators. Workday waits
for per-company board URLs. Job list/board APIs expose salary + skills +
experience so Discover/Pipeline cards can show them. `max_pairs: 1` when many
boards are enabled to protect free Apify credit.
**Why:** User asked for those boards; ATS boards duplicate free local adapters;
Monster’s prior actor 404’d (switched to `bebity/monster-jobs-scraper`, rental).
Glassdoor/Zip are rental extras, not defaults.
**Touches:** `sources/apify_boards.py`, `apify_adapter.py`, `jobs_api.py`,
`tracker_board.py`, JobCard/JobRow/Pipeline/DetailModal, Connections,
`profile.example.yml`, `tests/test_apify_naukri.py`.

## 2026-07-29 — Coverage > purity: Naukri enrichment + opt-in Apify
**Decision:** Keep Greenhouse/Lever/Ashby/aggregators as the free primary path.
Enrich the local Naukri adapter so salary/skills/experience survive into
`JobRecord`. Expand `portals.yml` with India/enterprise employers (Okta, GitLab,
Postman, PhonePe, Razorpay, …). Add an **opt-in** `apify` SourceAdapter
(LinkedIn + Naukri actors via `APIFY_TOKEN`) — same pattern as SerpAPI, never a
product default.
**Why:** A real Apify inventory run (~$0.20, free $5 credit) showed Naukri was
the richest India source (salary bands, skills, companies aggregators missed).
Local Naukri now returns captcha (`406`) often, so Apify is cheap insurance.
Claude's scrape undervalued ATS APIs only because that env couldn't call them —
Shortlistr already can; the miss was watchlist coverage + Naukri field loss.
**Touches:** `scrapers/naukri_scraper.py`, `sources/adapters/naukri_adapter.py`,
`sources/apify_client.py`, `sources/adapters/apify_adapter.py`,
`sources/registry.py`, `config.py`, `portals.yml`, `profile.example.yml`,
`.env.example`, Connections UI, `tests/test_apify_naukri.py`.

## 2026-06-30 — Six flow-coherence fixes (score → eval → gate → capture → apply)
**Decision:** Closed six logic gaps identified in the flow review:
1. `discover_and_filter()` now scores every job via `score_job()` before persist.
2. `auto_evaluate_pending()` extracted as shared helper; wired into discovery worker.
3. `evaluate_job_text()` accepts optional `job_id` and logs `mark_evaluated` failures.
4. `POST /jobs/{id}/apply-assist` requires `confirm: true` (403 without it).
5. `process_inbox()` (outcome capture) runs after `reflect()` in scheduler.
6. Apply runner page filters to `approved` only (not `evaluated`).
**Why:** spine was real but loops didn't close — discovery scored 0, manual scan
skipped auto-eval, apply-assist was ungated, outcomes never captured, evaluated
jobs leaked into apply queue.
**Touches:** `orchestrator/discovery.py`, `scheduler/scan_scheduler.py`,
`eval/service.py`, `api/main.py`, `workers/discovery_worker.py`,
`dashboard/app/apply/page.tsx`, `dashboard/src/lib/api/client.ts`.

## 2026-06-30 — Dashboard discover is async by default
**Decision:** the frontend sends `async_run=true` to `/jobs/discover`. The backend
enqueues the task and spawns a worker thread immediately. The frontend shows a toast
and polls `GET /jobs` every 3s for up to 60s to pick up results as sources finish.
**Why:** sync discover blocks the endpoint for 60-150s+ (Naukri sleeps + DuckDuckGo
timeouts). The Next.js proxy drops the connection after ~60s (`ECONNRESET`).
**Touches:** `dashboard/src/lib/api/client.ts`, `dashboard/src/hooks/useJobs.ts`,
`dashboard/app/inbox/page.tsx`, `dashboard/src/types/job.ts`,
`automation/api/main.py`.

## 2026-06-30 — Aggregators source skipped when user doesn't want remote
**Decision:** the `aggregators` source (RemoteOK, Himalayas, Remotive, WeWorkRemotely,
WorkingNomads, NoDesk, Jobspresso) is skipped entirely in the registry when
`WANTS_REMOTE` is False. Previously it ran every scan, fetched ~3400 remote-only jobs,
then the filter rejected all of them.
**Why:** wasting 5-10s fetching thousands of jobs that will all be filtered out is
pointless. The filter-level bypass (P1-6) was necessary but not sufficient — the fetch
itself should be skipped.
**Touches:** `automation/sources/registry.py`.

## 2026-06-30 — WANTS_REMOTE controls remote-source location bypass
**Decision:** remote-only sources (RemoteOK, Himalayas, Remotive, SearchDiscovery) only
skip the location check when `WANTS_REMOTE` is True — i.e. the user has at least one
remote term in `preferred_locations`. When all locations are cities, remote jobs are
filtered out like any other off-location result.
**Why:** unconditionally bypassing location checks for remote sources flooded city-only
users' inboxes with irrelevant "Remote" jobs.
**Touches:** `automation/config.py` (`WANTS_REMOTE`), `automation/pipeline/filter.py`,
`tests/test_location_targeting.py`.

## 2026-06-30 — Naukri is a first-class source adapter
**Decision:** Naukri uses the public `jobapi/v3/search` endpoint (no login) and is wired
into the discovery pipeline as `NaukriAdapter`. Search pairs are built dynamically from
`config.SEARCH_KEYWORDS × LOCATION_KEYWORDS` (no hardcoded titles/cities). `wfhType: "3"`
is only added when the location is a remote term.
**Why:** Naukri is the primary Indian job board. Hardcoded search pairs broke when the
profile changed; the adapter pattern makes it a standard pipeline source.
**Touches:** `automation/sources/adapters/naukri_adapter.py` (new),
`automation/sources/registry.py`, `automation/scrapers/naukri_scraper.py`,
`automation/config.py` (default enabled list).

## 2026-06-30 — Search discovery has a circuit breaker
**Decision:** `discover_from_search()` enforces a 30s total time cap and stops after 2
consecutive query failures. `FETCH_TIMEOUT` is 8s (down from 15s).
**Why:** DuckDuckGo HTML scraping is frequently blocked/down. Without a cap, 10+ queries
× 15s timeout = 150s+ stall, blocking the entire scan and causing proxy timeouts.
**Touches:** `automation/processors/search_discovery.py`.

## 2026-06-30 — Scheduler has a 120s boot grace period
**Decision:** `scan_is_due()` returns False for the first 120s after module load when
`last_scan_at` is null. Manual scans (dashboard button) still work immediately.
**Why:** on first boot, `last_scan_at` is null → `scan_is_due()` returns True instantly.
Combined with a manual dashboard scan, this causes duplicate scans.
**Touches:** `automation/scheduler/scan_scheduler.py`.

## 2026-06-30 — Semantic color tokens (success/warning/danger + lime-ink)
**Decision:** the design system now has `success`/`warning`/`danger` (each with a
`-soft` fill + ink text) and `lime-ink` (readable dark lime for text/icons, since
brand `lime` #dfff5e is too light for text). Components use these tokens, not raw
Tailwind palette colors. Token values intentionally match the Tailwind colors they
replaced, so the change was visual-neutral.
**Why:** the audit flagged off-token colors with no semantic equivalent; flattening
to lime/orange would lose green-vs-red meaning, and `text-lime-700` was a readable
accent that the flat `lime` token can't express.
**Touches:** `dashboard/app/globals.css`, `dashboard/tailwind.config.js`, Badge,
Button, AtsScoreCard, CvHtmlPreview, OfflineBanner + lime-ink usages.

## 2026-06-30 — A job's canonical id is always the URL hash
**Decision:** the DB primary key for a job is always `job_id_from_url(url)`
(16-hex). A source-provided id (RemoteOK numeric, WeWorkRemotely guid, href) is
never the key — it's stored in `metadata.source_job_id`. Enforced in
`JobRecord.__post_init__`, not per-scraper.
**Why:** the API validates `^[a-f0-9]{16}$`; any other id makes a job
non-actionable (400/404). Centralizing the invariant stops a single misbehaving
source from corrupting actionability.
**Touches:** `automation/models/job.py`, `automation/store/migrate_job_ids.py`,
`tests/test_job_id_canonical.py`.

## 2026-06-30 — First run is gated by onboarding
**Decision:** a user with no profile is redirected from `/dashboard` to
`/onboarding`, and onboarding step chips past the profile step are locked until a
profile is saved.
**Why:** landing on a populated, untargeted dashboard before setup is the top
first-time confusion; targeting needs a profile first.
**Touches:** `dashboard/app/dashboard/page.tsx`, `dashboard/app/onboarding/page.tsx`.

## 2026-06-30 — Preferred locations are authoritative for discovery
**Decision:** when `config/profile.yml → filters.preferred_locations` is set, it
**replaces** the broad India metro default in `LOCATION_KEYWORDS` (remote keywords are
still added for remote/any work modes). Empty → fall back to the metro default.
**Why:** users must be able to target one city (e.g. "Hyderabad only"). Previously
preferred locations were merged into a fixed metro list, so every Indian metro matched.
**Touches:** `automation/config.py` (import block + `reload_discovery_config`),
`automation/pipeline/filter.py` (`passes_title_location`).

## 2026-06-30 — Onboarding pre-fills the profile from the résumé
**Decision:** `/cv/upload` returns best-effort structured fields
(`automation/cv/profile_extract.py`, deterministic, no LLM). The onboarding Profile step
uses them to pre-fill name/email/phone/location/links/years/title and infer region +
preferred locations, so the **first scan is targeted, not global**.
**Why:** users shouldn't hand-type what's already in their résumé, and an untargeted
first scan feels broken.
**Touches:** `automation/cv/profile_extract.py`, `automation/api/main.py` (`/cv/upload`),
`dashboard/src/components/onboarding/ProfileStep.tsx`.

## 2026-06-30 — Pipeline UI reads the tracker board, not `status=all`
**Decision:** the Pipeline kanban consumes `GET /tracker/board` (status-prioritized,
includes `pipeline_status` + counts). `GET /jobs?status=all` is a catch-all that does not
join the pipeline table and must not back the kanban.
**Why:** `status=all` returned rows without `pipeline_status`, so every job counted as
"pending" and downstream columns were empty/misleading.
**Touches:** `dashboard/app/pipeline/page.tsx`, `automation/api/tracker_board.py`,
`automation/api/jobs_api.py`.

## 2026-06-30 — `skip` is a reversible application state
**Decision:** in the application status machine, `skip` can transition to `evaluated` /
`applied`. The pipeline machine already allows `skipped → pending`.
**Why:** a user who un-skips a job must be able to re-evaluate and apply; a terminal
`skip` blocked re-entry (`skip → applied` 400'd).
**Touches:** `automation/store/status.py` (`APPLICATION_TRANSITIONS`).

## (baseline) — Two separate state machines
**Decision:** pipeline status (`pending → evaluated → approved → submitted`, `skipped`)
is distinct from application status (`evaluated → applied → responded → …`). Both are
enforced in `automation/store/status.py`; the API handler validation must agree with
`PIPELINE_TRANSITIONS`.
**Why:** "where a job is in my queue" and "where an application stands with the employer"
are different lifecycles.

## (baseline) — Local-first, secrets never committed
**Decision:** everything runs on the user's machine. Secrets live in `.env` / OS keychain
via `automation/secrets_store.py`. `make reset` preserves `.env` + `portals.yml`.
**Why:** privacy + the product is single-user/local. Consequence: a post-reset machine
can have a saved LLM key but `provider: none` (key survives, profile is wiped).

## (baseline) — Eval runs in template or full-LLM mode
**Decision:** evaluation works without a key (template keyword scoring, ~3.x/5). Full
A–G LLM scoring needs **both** a provider in `profile.yml` and a key in `.env`.
**Why:** the app must be useful with zero setup; the LLM is an upgrade, not a gate.

## 2026-07-29 — Neutral dummy flow: no author identity in seed
**Decision:** First-run seed writes a placeholder `cv.md` only and does **not**
create `config/profile.yml`. Fit scoring reads titles from the live profile and
skills from the résumé; empty titles score 0 (complete onboarding). Disqualifiers
no longer hard-ban Product Manager / Data Analyst / etc.
**Why:** Author-specific location/role defaults made every clone search the author's market.
The product is résumé → targeting → matching jobs for *that* user.
**Touches:** `cv/sample_content.py`, `bootstrap/seed.py`, `profile_store.py`,
`processors/job_filter.py`, onboarding placeholders, `README.md`.

**Decision:** referrals get their own state machine (`automation/referrals/status.py`:
`routed → accepted → submitted → interviewing → hired | rejected | expired | cancelled`,
expired → routed re-route allowed), separate from pipeline/application machines; one
ACTIVE referral per (candidate, job) enforced by a partial unique index (v5.sql).
Multi-candidate tailoring (`automation/processors/sprint_tailor.py`) reads
`batch/candidates/<slug>/cv.md` × `jds/*` and renders via `render_cv_html` +
`generate_pdf_from_html` directly — NOT via `generate_cv_artifacts(md=...)`, because
that path overwrites the root `cv.md` user layer (`save_cv_markdown`). `evaluate_job_text`
gained an optional `cv_text=` param for per-candidate evals; empty url/job_id skips all
DB writes. Metrics (`referrals metrics`) split conversion raw-vs-tailored — the A/B the
first 10 raw referrals seeded.
**Why:** M1 anchor sprint went live early; the routed-referral log is the source of truth
for referral→interview conversion. Tests: `tests/test_referral_log.py`,
`tests/test_sprint_tailor.py`.
**Touches:** `store/db.py` (v5 migration), `store/migrations/v5.sql`, `automation/referrals/`,
`engage/tailor.py` (was processors/sprint_tailor.py), `eval/service.py`, `cli.py`, `Makefile`.

## 2026-07-25 — Engage core + testbed (M2 brain, transport-agnostic)
**Decision:** the WhatsApp conversation flow is built as a transport-agnostic core
(`automation/engage/core.py`: `handle_message`/`handle_upload` return plain replies)
with phone-keyed sessions (`engage_sessions`, v6.sql). The dashboard `/testbed` page
is a WhatsApp simulator hitting `/engage/*` endpoints; the future BSP webhook plugs
into the SAME handlers — no rewrite when WhatsApp goes live. Flow: consent (DPDP,
before any storage) → resume (upload or paste) → profile/employer confirm →
role cards (keyword-overlap ranking; LLM only tailors) → tailored PDF → explicit
YES → referral logged as routed. Own-employer confidentiality gate fails CLOSED
(`SHORTLISTR_ANCHOR_COMPANY` + alias normalization); "delete my data" purges session +
candidate workspace. Artifact serving is realpath-restricted to output/sprint/.
**Why:** BSP approval lag blocks WhatsApp; the testbed lets the full M2 journey be
built/tested now. Tests: `tests/test_engage.py` (8: journey, consent gate, fail-closed
employer gate, own-employer hiding, reject path, deletion, phone validation).
**Touches:** `automation/engage/`, `store/migrations/v6.sql`, `store/db.py`,
`api/main.py` (/engage/*), `dashboard/app/testbed/page.tsx`, `dashboard/src/lib/api/client.ts`.

## 2026-07-25 — Engage matcher: TF-weighted heuristic + LLM rerank
**Decision:** role matching is two-stage. Stage 1 (deterministic, always works):
term-frequency-weighted title/skill-family affinity — a skill mentioned 10× in the
resume is identity, one mention counts ~nothing; generic title words
(engineer/manager/project/full/stack…) carry zero signal; all-generic titles get a
0.25 prior so coverage decides. Stage 2: Groq reranks the top-8 shortlist to ≤5 with
candidate-facing "why" lines (strict-JSON prompt, silent fallback to heuristic order
on any failure). Employer extraction scans ONLY the parsed experience section
(projects sections say "Present" too) and checks the line after the heading
("Wipro Bangalore, India" layout). cv/parser.py heading matching is now tolerant
("TECHNICAL SKILLS & CORE COMPETENCIES" → skills).
**Why:** first real-resume simulation showed vague cards and a project name guessed
as employer; validated against 4 real resumes (SRE→SRE, Java→Java, tester→test roles).
**Touches:** `automation/engage/core.py`, `automation/cv/parser.py`, `tests/test_engage.py`.

## 2026-07-25 — Job bridge: discovery feeds the referral engine
**Decision:** the scraped `jobs` table and the anchor `jds/*.md` files are now one
inventory behind `automation/engage/roles.py:RoleCandidate` (`role_id` =
`file:<name>` | `db:<job_id>`). Candidates see REFERABLE roles first (anchor JDs, or
any company with a `referrers` row), then DIRECT-APPLY roles with the real URL and an
honest "no insider yet, we're looking" message. Locations are open-vocabulary
(inventory is global) but validated against actual job locations, so "Berlin" works
and "somewhere nice" re-asks. A candidate whose employer has openings is asked once
to become a referrer (`awaiting_referrer_optin` → `referrals/registry.py`).
Card composition blends both groups BEFORE the LLM rerank — referable roles carry a
+2.0 bonus and would otherwise fill every slot.
**Ingestion:** `make ingest` (cron, every 2h) calls the orchestrator directly, NOT
`scan_is_due` (its 120s boot grace never opens for a one-shot process), and forces
fetcher TTL to 3300s because DEFAULT_TTL was exactly the 2h cadence. `flock` on
`data/.ingest.lock` skips overlapping ticks. Upserts are batched (one connection);
the per-job path re-ran the migration ladder on every row.
**Lifecycle:** v7 adds `jobs.archived_at/last_checked_at/liveness/dead_strikes` —
columns absent from `upsert_job`'s SQL, so a re-scrape can never resurrect an
archived job. `make jobs-sweep` archives only on the SECOND consecutive dead verdict
(403/timeouts are `uncertain` and never count), and purges after 30 days only when no
referral/application/non-pending-pipeline row references the job.
**Landmine fixed:** liveness timestamps must use SQLite's `%Y-%m-%d %H:%M:%S`, not
isoformat() — 'T' > ' ' makes mixed-format string comparison silently never match.
**Why:** the founder wants referral-first with direct-apply fallback and hands-off
job refresh. Tests: `tests/test_job_lifecycle.py` (17), `tests/test_engage_db_roles.py` (14).
**Touches:** `store/{db,queries,pipeline_feed}.py`, `store/migrations/v7.sql`,
`jobs/{ingest,liveness_sweep,cli}.py`, `engage/{core,roles}.py`, `referrals/{log,registry}.py`,
`processors/sprint_tailor.py`, `cli.py`, `Makefile`, `scripts/setup-job-crons.sh`.

## 2026-07-25 — Referrer job intake: link-first, screenshot fallback
**Decision:** referrers can add openings at their own company by pasting the PUBLIC
posting link (say SHARE, or just paste a URL mid-conversation); a screenshot is a
fallback that is OCR'd (tesseract) only to extract a URL. `automation/engage/intake.py`
verifies the URL resolves to a real posting via the existing
`scrapers/ats_url_resolver.resolve_job_url` (Greenhouse/Lever/Ashby + generic careers
HTML) before anything is stored, then upserts it with `source='referrer'` and
auto-registers the sharer as a referrer for that company (so the role shows as
referable). A referrer-shared URL also REVIVES an archived job — they have better
information than our last HTTP check.
**Hard rule (CEO review B3):** publicly-verifiable postings only. We never create a
job from OCR text alone, because an unverifiable screenshot of an internal portal is
exactly what we promised not to ingest — the referrer, not us, carries that policy
risk. Unresolvable links are declined with an explicit "we can't take internal-only
systems" message.
**Landmine fixed:** the image path originally called `submit_screenshot` (which
inserts) and then `_handle_shared_job` (which inserts again). Images now extract the
URL and delegate, so screenshot and pasted link share ONE submission path.
**Why now:** the referrer registry existed but registered referrers had nothing to do
— this is the months-1-6 referrer value prop the CEO review flagged as missing.
Tests: `tests/test_engage_intake.py` (17).
**Touches:** `engage/intake.py` (new), `engage/core.py` (SHARE command,
`awaiting_shared_job`, image upload branch), `automation/requirements.txt`.

## 2026-07-25 — Referrer posts openings from a screenshot (no URL)
**Decision:** the primary referrer flow is a screenshot of an internal openings LIST
with no URL in it. `engage/intake.extract_openings()` OCRs it (tesseract) and has the
LLM structure the messy text into role records; when no LLM is configured a heuristic
row-parser handles it. Nothing is stored until the sharer confirms what we read —
OCR misreads, and confirmation is the quality gate. Confirmed roles become jobs with
`source='referrer'` and a synthetic `referrer://<company>/<hash>` URL (jobs.url is NOT
NULL UNIQUE, and the scheme is how the liveness sweep knows to skip them). The sharer
is auto-registered as referrer for that company, so the roles show as referable.
**Data minimization:** only title, location, seniority-as-a-word and req id are kept.
Band/grade codes (B4, L5) are compensation data and are stripped by `_clean_seniority`
in both the LLM prompt and post-processing; the raw image is never stored.
**Card composition:** three groups each get reserved slots (`ATTESTED_SLOTS`,
`DIRECT_SLOTS`) via `_guarantee()`. Without it the anchor's rich JDs won every slot and
a referrer who posted openings would never receive candidates for them — defeating the
point of posting.
**Scoring fix:** `title_aff` divided by `max(len(disc), 2)`, which halved the affinity
of short precise titles ("Senior Java Developer"). The TF weighting already prevents a
single passing mention scoring full affinity, so it now divides by `len(disc)`.
**Query fix:** `MIN_JD_CHARS` screens out stub SCRAPED postings; referrer-attested
roles are legitimately terse and are exempted (`source = 'referrer' OR length > N`).
**Loop proven live:** referrer screenshot → 4 roles extracted → confirm → published →
candidate sees "Senior Java Developer — Wipro" as referable → tailored PDF → approves →
referrer inbox shows the candidate with a download link → REFER marks it submitted.
Tests: `tests/test_referrer_openings.py` (18).
**Touches:** `engage/intake.py`, `engage/core.py`, `engage/roles.py`,
`referrals/registry.py` (inbox/companies_for), `store/queries.py`.

## 2026-07-25 — User-submitted jobs: employer-match rule + admin approval
**Decision:** anyone (candidate, referrer, passer-by) can share openings — a
screenshot of an internal list, a LinkedIn hiring post, a multi-company round-up.
Two rules govern what happens next:
1. **A referral claim requires employment.** `intake.can_refer(submitter_employer,
   role_company)` decides per ROLE, not per submission: a Gojek employee posting a
   Gojek role becomes its referrer (`jobs.referrer_phone`); the same person sharing
   a Merck role does not. One screenshot can produce both. If the submitter's
   employer is unknown, the bot asks "Do you work at X?" — it never assumes.
2. **Nothing user-submitted reaches candidates unreviewed.** v8 adds
   `jobs.review_status` (NULL = scraped by us, auto-trusted; 'pending'/'approved'/
   'rejected' for submissions). `fetch_candidate_jobs` only returns NULL/approved.
   `make jobs-review list|approve|reject` is the admin gate; APPROVAL is what
   activates the referrer, and rejection clears the claim.
**Extraction:** tesseract OCR → Groq structures the messy text into
{title, company, location, seniority, req_id, url}. Company is the EMPLOYER HIRING,
which is usually not the poster. Explicitly dropped: band/grade codes (compensation
data — `_clean_seniority` only accepts words like Senior/Lead), hiring-manager
names, and the poster's own headline (a "Head of SRE at Gojek" byline is not a
vacancy). The screenshot itself is never stored.
**Landmine fixed:** images used to OCR twice and prefer any URL found. Real posts
list several roles each with its own link, so images now always go through
`extract_openings` and links are captured per role.
**Why:** the founder's rule — "if I work at Wipro and post another company's
opening, that must not become a referral" — plus admin approval before candidates
see anything. Tests: `tests/test_submitted_job_rules.py` (16),
`tests/test_referrer_openings.py` (18), `tests/test_engage_intake.py` (18).
**Touches:** `engage/intake.py`, `engage/core.py`, `engage/roles.py`,
`store/{db,queries}.py`, `store/migrations/v8.sql`, `jobs/review.py` (new),
`cli.py`, `Makefile`.

## 2026-07-25 — Layer model: sprint_tailor moved to engage/tailor.py
**Decision:** `processors/sprint_tailor.py` was a Layer 3 (platform) module living in a
Layer 2 (local tool) package — it serves `batch/candidates/` and `output/sprint/`, never
the founder's own `cv.md`. Moved to `automation/engage/tailor.py`. The user-facing
`make sprint-tailor` command and CLI verb are **unchanged** on purpose; only the module
path moved. Verified beforehand that nothing in Layers 1/2 imported it.
**The layer rule this enforces (see CLAUDE.md):** Layer 3 may call Layer 1 freely, must
never touch Layer 2's single-user state, and Layer 2 must never call Layer 3. Keeping
that true is what makes the Phase 2 extraction a move rather than a rewrite.
**Touches:** `engage/tailor.py` (moved), `engage/{core,roles}.py`, `cli.py`,
`tests/test_tailor.py` (renamed) + 5 engage test files.

## 2026-07-25 — Data boundary: two databases, one schema
**Decision:** Layer 3 gets its own SQLite file, `data/platform.db`. The owner's
personal job search stays in `data/shortlistr.db` — the only database anyone who clones
the repo ever gets. Both run the identical schema/migration ladder, so a row means
the same thing on either side and there is no second schema to maintain.
**Mechanism:** a `contextvars` ContextVar holds the active DB path; `_connect()`
resolves it at call time. Layer 3 public entry points are decorated with
`@platform_scoped` (`engage/scope.py`), so Layer 1 helpers they call
(`upsert_jobs`, `audit`, …) transparently write to the platform file. The boundary
is enforced in one place instead of at 78 call sites. `store.platform_db()` is the
read helper for admin tooling and tests.
**Bridge:** `make publish ARGS='add <job_id>'` copies a job from personal → platform.
Nothing is published automatically. The owner's private workflow fields (fit_score,
fit_reason, notes) deliberately do not cross. Owner-published jobs get
`review_status = NULL` (trusted, no moderation) vs `pending` for user submissions.
When Layer 3 moves to a server this becomes an authenticated API call with the same
command shape.
**Consequence worth knowing:** purge guards are per-database. A referral in
platform.db does NOT block the owner purging their own archived copy — correct,
because the platform holds its own copy of any published job.
**Migration:** `scripts/migrate-platform-data.py` moved the existing 5 referrals,
3 sessions and 1 referrer across (backup written first, verified before deleting).
Tests: `tests/test_data_boundary.py` (16).
**Touches:** `store/db.py`, `engage/scope.py` (new), `engage/{core,roles,intake}.py`,
`referrals/{log,registry}.py`, `jobs/{review,publish}.py` (publish new), `cli.py`,
`Makefile`, `scripts/migrate-platform-data.py` (new).

## 2026-07-25 — Repo split: the platform moved to a private repo
**Decision:** Layer 3 now lives in `~/Documents/referral-engine` (private). This
repo is the engine plus the single-user tool: anyone who clones it gets a complete
personal job search and nothing else — no /engage routes, no testbed, no referral
or moderation commands, and no tables holding other people's data.
**Dependency direction:** the platform imports this repo rather than vendoring it.
`referral-engine/bootstrap.py` puts `<engine>/automation` on sys.path (resolved from
$SHORTLISTR_ENGINE or the sibling `../shortlistr-main`) and sets `SHORTLISTR_PLATFORM_DB` so
the platform owns its own data directory. Module names are unchanged, so the moved
code needed no import rewriting beyond `jobs.review`/`jobs.publish` → `admin.*`
(the engine keeps a `jobs` package for ingest/liveness, which would otherwise be
shadowed).
**The bridge:** `publish` moved to the platform repo. It reads the owner's personal
DB and writes the platform DB — the only path a job takes between them, still one
job at a time. When the platform moves to a server this becomes an API call.
**What stayed:** `jobs/ingest.py` and `jobs/liveness_sweep.py` (engine — the owner's
own discovery), `store/using_platform_db()` (a generic second-store hook; nothing
in this repo enters that scope).
**Verification:** public repo 303 pass / 3 pre-existing fail, tsc clean, API boots
with 60 routes and zero /engage. Platform repo 151 pass. Neither tracks any PII.
