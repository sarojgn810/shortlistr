# Mode: inbox — Process URL Inbox

Process job URLs accumulated in `data/pipeline.md`. The user adds URLs whenever they want, then runs `/shortlistr inbox` to process them all.

## Workflow

1. **Read** `data/pipeline.md` → find `- [ ]` items in the `## Pending` section (legacy alias: `## Pendientes`)
2. **For each pending URL**:
   a. Compute next sequential `REPORT_NUM` (list `reports/`, take highest number + 1)
   b. **Extract JD** using Playwright (browser_navigate + browser_snapshot) → WebFetch → WebSearch
   c. If URL is not accessible → mark as `- [!]` with note and continue
   d. **Run full evaluate-full pipeline**: A–G evaluation → Report .md → PDF (if score >= 3.0) → Tracker
   e. **Move from Pending to Processed**: `- [x] #NNN | URL | Company | Role | Score/5 | PDF ✅/❌`
3. **If 3+ pending URLs**, launch agents in parallel (Agent tool with `run_in_background`) for speed.
4. **When done**, show summary table:

```
| # | Company | Role | Score | PDF | Recommended action |
```

## pipeline.md format

```markdown
## Pending
- [ ] https://jobs.example.com/posting/123
- [ ] https://boards.greenhouse.io/company/jobs/456 | Company Inc | Senior PM
- [!] https://private.url/job — Error: login required

## Processed
- [x] #143 | https://jobs.example.com/posting/789 | Acme Corp | AI PM | 4.2/5 | PDF ✅
- [x] #144 | https://boards.greenhouse.io/xyz/jobs/012 | BigCo | SA | 2.1/5 | PDF ❌
```

## Smart JD detection from URL

1. **Playwright (preferred):** `browser_navigate` + `browser_snapshot`. Works with all SPAs.
2. **WebFetch (fallback):** For static pages or when Playwright is unavailable.
3. **WebSearch (last resort):** Search secondary portals that index the JD.

**Special cases:**
- **LinkedIn**: May require login → mark `[!]` and ask user to paste text
- **PDF**: If URL points to a PDF, read it directly with Read tool
- **`local:` prefix**: Read local file. Example: `local:jds/linkedin-pm-ai.md` → read `jds/linkedin-pm-ai.md`

## Automatic numbering

1. List all files in `reports/`
2. Extract number from prefix (e.g., `142-medispend...` → 142)
3. New number = max found + 1

## Source sync

Before processing any URL, verify sync:
```bash
python3 -m automation.cli sync-check
```
If out of sync, warn the user before continuing.
