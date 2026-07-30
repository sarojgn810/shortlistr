# Competitive positioning — judgment-first vs volume auto-apply

**Reference competitor:** [Tsenta](https://tsenta.com/) (YC S26)  
**Last reviewed:** 2026-06  
**Shortlistr stance:** Compete on **judgment and intention**, not application volume.

Related: [ARCHITECTURE.md](ARCHITECTURE.md)

---

## Executive summary

| | **Tsenta** | **Shortlistr** |
|---|------------|-------------|
| **One-liner** | AI agent that auto-applies to hundreds of jobs per week | Local-first, judgment-first job search: find → **score honestly** → tailor → apply with intent |
| **Primary metric** | Applications submitted / speed to first 100 applicants | Fit score, report quality, interview conversion |
| **Default behavior** | Submit at scale (approve optional) | **Never auto-submit** without user review |
| **Data** | Cloud SaaS | Local SQLite + gitignored profile/CV |
| **Buyer** | Students, mass search, OPT/sponsorship filters | Senior/niche roles, quality-conscious searchers |

**Do not try to win:** “600 applications per month” or Workday-at-scale black-box submit.  
**Do win:** “Here are the 5 roles worth your week — with receipts, prep, and why.”

---

## What Tsenta ships (baseline to beat on UX, not on ethics)

Source: [tsenta.com](https://tsenta.com/), YC listing, AI disclosure page.

### Four-stage pipeline

1. **Find** — Watches 50,000+ career pages (Workday, Greenhouse, Lever, Ashby, 15+ ATSes). Match feed in seconds. Paste URL to queue.
2. **Prep** — Per-role résumé + cover letter rewrite; keyword-aligned; **diff shown before send**.
3. **Apply** — End-to-end form fill and **submit** on 19 ATSes; open-ended answers “in your voice”; **receipt** per application (fields, files, answers).
4. **Track** — Recruiter emails routed to the right job; status pipeline (Applied → Viewed → Replied → Interview).

### Distribution

- Web dashboard (`app.tsenta.com`)
- Desktop (Mac/Win/Linux), mobile (iOS/Android)
- Chrome extension
- iMessage / WhatsApp bots
- **MCP** for AI agents

### Pricing (volume-based)

- 25 free applications (no card)
- ~$19/mo → 600 apps · $39/mo → 1,500 · $99/mo → 4,500

### Positioning hooks they use

- “Be in the top 100 applicants”
- “Hundreds of applications a week”
- “Zero spreadsheets”
- OPT / sponsorship filtering on forms

---

## What shortlistr has today (honest inventory)

### Strengths (differentiation)

| Capability | Where it lives |
|------------|----------------|
| **A–G evaluation** (archetypes, legitimacy, negotiation) | `modes/evaluate.md`, `modes/evaluate-full.md` |
| **Structured EvalService** (JSON schema, golden tests) | `automation/eval/`, `make evaluate` |
| **Discovery architecture** | `SourceAdapter`, `SourceRegistry`, unified filter |
| **Local system of record** | `data/shortlistr.db`, `make export-pipeline` |
| **Ethical guardrails** | agent guardrails config, apply queue, no default auto-submit |
| **Interview prep + story bank** | `interview-prep/`, evaluation reports |
| **Portal + hybrid discovery** | `portals.yml`, search queries, URL resolver |
| **Career workflow depth** | Compare offers, contact outreach, patterns, follow-up |

### Gaps vs Tsenta (product surface)

| Gap | Tsenta | Shortlistr today |
|-----|--------|----------------|
| Polished web inbox | ✅ Core | Scaffold (`/inbox` HTMX only) |
| E2E ATS submit (Workday) | ✅ 19 ATSes | Partial (email GH/Lever/Ashby; no Workday bot) |
| Application receipt UI | ✅ Per submit | Audit log only |
| Résumé diff before send | ✅ | PDF gen; no diff view |
| Recruiter reply routing | ✅ Auto | Drafts file; manual |
| Match explanation UI | Match % | `fit_score` + eval blocks (IDE) |
| Multi-channel (SMS, ext) | ✅ 8 surfaces | CLI + IDE + cron |
| Scale of page watch | 50k pages | User `portals.yml` + aggregators |

---

## Positioning wedge

### Tagline options (pick one for UI/marketing later)

1. **“Apply to fewer jobs. Win more of them.”**
2. **“The job agent that scores before it submits.”**
3. **“Job search for people who won’t spam recruiters.”**

### Target user (primary)

- **Senior IC / staff+** in platform, SRE, applied AI, backend
- **India remote / global remote** with comp and legitimacy concerns
- Already using an AI IDE; wants **local data** and **transparent** automation
- Rejects spray-and-pray; will pay for **judgment + prep**, not raw volume

### Target user (secondary)

- Career changers who need **evaluation and narrative**, not 400 generic apps
- Operators who outgrew spreadsheet trackers but don’t trust black-box SaaS

### Anti-persona (do not optimize for)

- “Apply to 500 jobs this month” undergrad mass search
- Users who want zero involvement before submit
- Teams needing hosted multi-tenant SaaS on day one (Phase 2 later)

---

## Competitive matrix (feature level)

| Feature | Tsenta | Shortlistr | Our angle |
|---------|--------|---------|-----------|
| Job discovery | 50k pages, always-on | Registry + portals + aggregators | Depth over breadth; user-curated watchlist |
| Fit scoring | % match | 0–100 fit + **0–5 eval** + legitimacy | **Explain why** (blocks A–G) |
| Auto-submit | Default path | Opt-in only; ethical veto | Trust, recruiter respect |
| Résumé tailoring | Per-role rewrite + diff | `generate_cv` / PDF template | Add diff + company variants |
| Cover letter | Generated per role | `cover_letter.py` + LLM | Same; show in receipt |
| Apply receipt | Field-level receipt | Needs build | See roadmap |
| Tracker | In-app pipeline | SQLite + `applications.md` + Excel | Unify in UI |
| Interview prep | Light / unclear | Story bank, company prep files | **Major differentiator** |
| Offer compare / negotiate | No | `modes/ofertas`, reports | **Major differentiator** |
| MCP / agents | `tsenta.apply` | CLI + skill; MCP TBD | `shortlistr.evaluate`, `discover` |
| Pricing | Per application volume | TBD (judgment-tier, not app-tier) | e.g. free local + paid eval/cloud |

---

## What to steal (patterns, not positioning)

These are **UX/product patterns** worth matching when UI work starts (design standards TBD):

1. **Single pipeline screen** — pending → prep → approved → submitted → replied
2. **Approve-before-send** with visible diff (résumé + cover letter)
3. **Application receipt** — immutable record of what was sent
4. **Paste URL → queue** — already have resolver + SQLite
5. **“Why this match”** panel — map `fit_score` + eval blocks to human copy
6. **Agent/MCP tools** — expose judgment layer to Claude/Cursor, not just apply

## What not to copy

- Volume pricing and “hundreds per week” marketing
- Default unattended submit on Workday/LinkedIn (ToS + ethics)
- Black-box cloud-only profile (conflicts with local-first story)
- Match-% without legitimacy / scam-job checks (Block G)

---

## Strategic responses (FAQ for future you)

**“Why not just use Tsenta?”**  
Tsenta optimizes for application count. Shortlistr optimizes for **decision quality**: legitimacy, archetype fit, interview prep, and negotiation. You apply to fewer roles with higher expected value.

**“Can we add auto-apply later?”**  
Yes, **assistive** apply (fill forms, user clicks Submit) before **agentic** apply. Workday E2E only with explicit opt-in and receipts. Never default mass submit.

**“Do we need 50k pages?”**  
Not to win the wedge. Need **reliable** coverage for the user’s watchlist + aggregators + alerts. Quality of filter and eval matters more than raw page count.

**“Hosted SaaS vs local?”**  
Phase 1: local excellence. Phase 2: optional hosted sync for inbox/UI. Position local as **privacy + control**; cloud as **convenience** for non-technical users later.

---

## Success metrics (judgment-first)

| Metric | Tsenta-style (avoid as North Star) | Shortlistr-style (prefer) |
|--------|--------------------------------------|-------------------------|
| Primary | Apps submitted / week | % of evaluated jobs ≥ 4.0/5 acted on |
| Quality | Match % | Eval score calibration vs user override |
| Outcome | Time to first apply | Interview rate per **approved** application |
| Trust | Receipts | Receipts + **eval report** linked to apply |
| Retention | Credit burn | Weekly active **evaluations** + pipeline cleared |

---

## Document history

| Date | Change |
|------|--------|
| 2026-06 | Initial positioning vs Tsenta after Phase 1 architecture + hardening |
