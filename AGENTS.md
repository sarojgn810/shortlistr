# Shortlistr — AI Job Search Pipeline

See `docs/ARCHITECTURE.md` for layout, data contract, and flow.

## Data Contract (critical)

**User layer (never overwrite):** `cv.md`, `config/profile.yml`, `modes/_profile.md`, `portals.yml`, `data/*`, `reports/*`, `output/*`, `interview-prep/*`

**System layer:** `modes/_shared.md`, `modes/*.md`, `automation/` code, `templates/`, `Makefile`

Put personalization in `modes/_profile.md` or `config/profile.yml` — not `_shared.md`.

## Skill modes (`/shortlistr`)

| Intent | Mode file | Command |
|--------|-----------|---------|
| Paste JD or URL | `evaluate-full.md` | `/shortlistr {URL}` |
| Evaluate only | `evaluate.md` | `/shortlistr evaluate` |
| Process inbox | `inbox.md` | `/shortlistr inbox` |
| Generate PDF | `generate-cv.md` | `/shortlistr generate-cv` |
| Scan portals | `scan.md` | `/shortlistr scan` |
| Tracker | `tracker.md` | `/shortlistr tracker` |
| Apply assistant | `apply.md` | `/shortlistr apply` |

Legacy aliases: `oferta`→evaluate, `pipeline`→inbox, `pdf`→generate-cv, `auto-pipeline`→evaluate-full.

Router: `skills/shortlistr/SKILL.md`

## First Run — Onboarding

Check silently: `cv.md`, `config/profile.yml`, `modes/_profile.md`, `portals.yml`. Copy templates if missing. Create `data/applications.md` tracker if missing.

## Ethical Use

- Never submit without user review. Apply-assist may prefill forms; **you** click Submit.
- There is no LinkedIn Easy Apply / Naukri auto-apply / unattended email-send path.
- Discourage applications below 4.0/5.

## Offer Verification

Use Playwright (navigate + snapshot) to confirm postings are live. Batch fallback: `**Verification:** unconfirmed (batch mode)`.

## Pipeline integrity

- Add tracker rows via `batch/tracker-additions/*.tsv` → `make merge` (or `python3 -m automation.cli merge`)
- Update existing `data/applications.md` rows directly
- Reports need `**URL:**` and `**Legitimacy:** {tier}`

### Canonical States

Source: `templates/states.yml` — `Evaluated`, `Applied`, `Responded`, `Interview`, `Offer`, `Rejected`, `Discarded`, `SKIP`

### TSV Format

Write one TSV file per evaluation to `batch/tracker-additions/{num}-{company-slug}.tsv` (9 tab-separated columns):

```
{num}\t{date}\t{company}\t{role}\t{status}\t{score}/5\t{pdf_emoji}\t[{num}](reports/...)\t{note}
```

Column order: num, date, company, role, status, score, pdf, report link, notes. Status comes before score (merge script swaps for applications.md).

## CV source

`cv.md` is canonical. Optional `article-digest.md` for proof points. Never hardcode metrics.
