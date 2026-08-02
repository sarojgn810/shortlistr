# Mode files

Each file defines instructions for one `/shortlistr` command. The router is `skills/shortlistr/SKILL.md`.

| File | Command | Purpose |
|------|---------|---------|
| `evaluate.md` | `/shortlistr evaluate` | Score a job (blocks A–G), save report, update tracker — no PDF |
| `evaluate-full.md` | `/shortlistr {URL}` or `/shortlistr evaluate-full` | Full flow: evaluate + report + PDF + tracker |
| `inbox.md` | `/shortlistr inbox` | Process pending URLs in `data/pipeline.md` |
| `generate-cv.md` | `/shortlistr generate-cv` | Tailored ATS CV PDF for a role |
| `scan.md` | `/shortlistr scan` | Discover jobs from configured portals |
| `tracker.md` | `/shortlistr tracker` | Show and update `data/applications.md` |
| `apply.md` | `/shortlistr apply` | Help fill live application forms |
| `_shared.md` | (always loaded) | Scoring rules, ethics, tools — system defaults |
| `_profile.md` | (always loaded) | Your archetypes, narrative, comp targets — you customize |

**Legacy command aliases:** `oferta`→evaluate, `pipeline`→inbox, `pdf`→generate-cv.
