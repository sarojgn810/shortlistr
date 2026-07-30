---
name: shortlistr
description: AI job search — evaluate offers, generate CVs, scan portals, track applications
user_invocable: true
args: mode
argument-hint: "[evaluate | evaluate-full | inbox | generate-cv | scan | tracker | apply]"
---

# shortlistr — Router

Load mode instructions from `modes/{mode}.md`. Shared rules are in `modes/_shared.md`.

## Mode routing

| Input | Mode file | What it does |
|-------|-----------|--------------|
| (empty) | *(inline menu below)* | Show command menu |
| JD text or URL | **`evaluate-full`** | Evaluate + report + PDF + tracker |
| `evaluate` | `evaluate.md` | Evaluate only (no PDF) |
| `evaluate-full` | `evaluate-full.md` | Same as pasting a JD/URL |
| `generate-cv` | `generate-cv.md` | Tailored CV PDF only |
| `tracker` | `tracker.md` | Application status overview |
| `inbox` | `inbox.md` | Process `data/pipeline.md` inbox |
| `apply` | `apply.md` | Live application form assistant |
| `scan` | `scan.md` | Portal scanner |

**JD auto-detect:** If `{{mode}}` is not a sub-command and looks like a JD (keywords: responsibilities, requirements, qualifications, or an http/https URL), run **`evaluate-full`**.

### Legacy command aliases (still supported)

| Old command | Maps to |
|-------------|---------|
| `oferta` | `evaluate` |
| `auto-pipeline` | `evaluate-full` |
| `pipeline` | `inbox` |
| `pdf` | `generate-cv` |

## Discovery menu

```
shortlistr — Command Center

  /shortlistr {JD or URL}     → evaluate-full (report + PDF + tracker)
  /shortlistr evaluate        → evaluate only (no PDF)
  /shortlistr evaluate-full   → same as pasting a JD
  /shortlistr inbox           → process data/pipeline.md inbox
  /shortlistr generate-cv     → tailored CV PDF
  /shortlistr scan            → scan configured portals
  /shortlistr tracker         → application status
  /shortlistr apply           → live application assistant
```

## Context loading

**`_shared.md` + mode file:** `evaluate-full`, `evaluate`, `generate-cv`, `apply`, `inbox`, `scan`

**Mode file only:** `tracker`

## Structured eval (Python EvalService)

For `evaluate` and `evaluate-full`, **first** run the structured eval CLI (one brain, two UIs):

```bash
make evaluate ARGS="URL=<job-url>"
# or from repo root:
python3 -m automation.cli evaluate <job-url>
```

Use the JSON output (`score`, `legitimacy`, `blocks`) as input to your A–G report. If the CLI fails (no Python env), fall back to mode-only evaluation.

**Subagent (3+ URLs or Playwright):** `scan`, `apply`, `inbox` — delegate to a general-purpose agent with the mode file injected.

Execute instructions from the loaded mode file.
