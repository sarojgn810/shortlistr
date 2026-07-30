# shortlistr — Architecture

Local-first AI job-search agent. Everything runs on your machine; the LLM is
pluggable (cloud key now, bundled local model later). The defining trait is the
**outcome feedback loop** — it learns from who replies vs. ghosts and adapts.

## Flow

```
discover → evaluate → prep → apply (assisted) → track → learn ↵ (feeds back into scoring)
```

## Layers

```
Front-ends    Next.js dashboard (:3000)   ·   chat panel + Telegram bot
   │ same-origin /api proxy
API           FastAPI (:8787)  /jobs /cv /tracker /applications /settings /agent/* /outcomes/*
   │
Agent layer   registry (tools: read|write|submit) · permission gate · dispatch (gate→route)
              connectors (MCP client) · channels (Gmail/SMTP) · memory (learnings)
   │
Services      sources/scrapers · eval (A–G + heuristic) · cv (gen/ATS) · prep
              apply (Playwright) · outcomes (capture/reflect/adapt) · scheduler
   │
State         SQLite shortlistr.db (schema v4) · OS keychain (secrets)
              cv.md · output/ · reports/ · config/profile.yml  (all gitignored)
```

## Data model — `data/shortlistr.db` (schema v4)

System of record. Tables: `jobs`, `pipeline` (pending→evaluated→approved→submitted),
`applications` (applied→responded→interview→offer/rejected), `eval_results` (A–G JSON),
`application_receipts`, `worker_queue`, `runs`, `audit_log`, `user_settings` (JSON blobs),
`learnings` (long-term memory, v4), `tenants`/`users` (single-tenant `default`).
Migrations via `store/db.py` ladder (`store/migrations/v2–v4.sql`); foreign keys ON.

Files: `cv.md` (canonical CV), `output/` (CV PDFs), `reports/*.md`, `interview-prep/`.

## Agent system (the spine)

- **Tool registry** (`agent/registry.py`) — every capability is a `Tool` with a side-effect
  class: `read` / `write` / `submit`.
- **Permission gate** — `read`/`write` flow; `submit` (apply-assist, `channel.send`, external
  MCP writes) require explicit confirm or an autopilot allowlist. Generalizes "never auto-submit."
- **Dispatch** (`agent/dispatch.py`) — one `call_tool(name, args, confirm)`: gate → route
  built-in or MCP. Exposed as `POST /agent/call` (403 when gated, audited).
- **MCP client** (`connectors/`) — connect outbound to user-configured MCP servers; their tools
  auto-register (`mcp.<server>.<tool>`, inferred side-effect, default `submit`) and inherit the
  gate. Package is `connectors/` (not `mcp/`) to avoid shadowing the `mcp` SDK.
- **Channels** (`channels/`) — uniform `read_inbox`/`draft`/`send`; Gmail + generic SMTP/IMAP.
  `send` is gated.
- **Memory** (`memory/`) — `learnings` (semantic), `audit_log` (episodic), working memory
  (settings JSON). Keyword search with a seam for local embeddings.

## Outcome feedback loop (`outcomes/`)

- **Capture** — inbound mail classified (rejection/interview/offer), matched to an application,
  status transitioned (high-confidence auto, audited/reversible).
- **Reflect** — conversion stats by company/source/score-band → idempotent `learnings`
  ("deprioritize" on ghosts, "prioritize" on ≥40% response); runs on the scan cadence.
- **Adapt** — bounded, transparent score adjustment in `job_filter.score_job` (delta + reason
  in `fit_reason`); learnings injected into the eval prompt; `GET /outcomes/insights` + UI card.

## Conversational control plane (chat + Telegram)

A platform-agnostic **chat core** (`agent/chat.py`) turns natural language into answers and
**gated** tool calls via the registry + dispatch. Two front-ends share it: a dashboard chat
panel (`POST /agent/chat`) and a Telegram bot (`connectors/telegram.py`, long-poll — the laptop
dials out, nothing exposed). Messaging directions: **outbound** notifications go through
MCP/Channels (any platform); **inbound** control needs a per-platform receiver (Telegram now;
Slack/WhatsApp later as thin adapters on the same core).

## Security

Secrets live in the **OS keychain** via `secrets_store.py` (keychain-first, `.env` fallback,
one-time migration): LLM key, email/LinkedIn/Naukri creds, MCP + bot tokens. `setup_cron.sh` no
longer writes passwords to `~/.zshrc`/crontab. Local single-user threat model; the API is open
on loopback by design (set `SHORTLISTR_API_TOKEN` before any non-loopback exposure).

## Running

```
make dev        # API (auto-reload) + scheduler + dashboard → http://localhost:3000
make api        # API only (no reload; stable serving)
make scheduler  # background scans + reflection
make test       # full test suite
```

First-run: `cd automation && python3 setup.py` (or dashboard onboarding) writes
`config/profile.yml` + stores secrets in the keychain.

## Config — `config/profile.yml`

`candidate` · `filters` (**work_mode** remote|hybrid|onsite|any + **region** anywhere|india,
salary floors, target titles) · `application` (website, notice_period, current/expected CTC,
how_heard) · `llm` · `email` · `mcp_servers` (name, transport, command/url, `secret_ref`).
Secrets are never stored in YAML.

## Ethics

- Never auto-submit applications or send external messages without confirmation
  (enforced by the `submit` side-effect class + permission gate).
- Score honestly; outcome-driven adjustments are bounded and shown in `fit_reason`.

## Roadmap status

- ✅ Foundations — keychain · tool registry + gate · memory
- ✅ Connect-your-apps — Channels + MCP client
- ✅ Outcome feedback loop — capture / reflect / adapt
- 🔄 Conversational control plane — chat core + dashboard panel + Telegram bot
- ⏭ Deferred — bundled quantized local LLM (packaging TBD)
