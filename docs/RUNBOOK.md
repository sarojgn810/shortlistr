# 🤖 How to Run Your Job Bot
### Simple guide — no tech jargon

---

## 🧠 What does this bot do?

Think of it like having a robot assistant who wakes up every morning at **9 AM**, goes to 20+ job websites, reads thousands of job postings, throws away the ones that don't match (on-site, low salary, wrong title), keeps only the good ones, and puts them in a neat list for you to review each morning.

You just look at the list, say YES or NO, and the bot handles the rest.

---

## 🗂️ Where are the files?

Everything lives in one folder on your Mac:
```
Documents → shortlistr → shortlistr → automation
```

Open Terminal (press `Cmd + Space`, type `Terminal`, press Enter) and type:
```bash
cd ~/shortlistr/automation
```
Press Enter. You're now "inside" the bot's folder.

---

## 🔧 PART 1 — First-Time Setup (do this ONCE, never again)

### Step 1 — Run the setup wizard

In Terminal, paste this and press Enter:
```bash
cd ~/shortlistr/automation
bash setup_cron.sh
```

It will ask you **two questions**:

**Question 1:** LinkedIn password (for your LinkedIn account)
- Type your password (the letters won't show — that's normal, it's hidden)
- Press Enter

**Question 2:** Naukri password (for your Naukri account)
- Type your password
- Press Enter

When it finishes you'll see: `✅ Setup Complete!`

---

### Step 2 — Connect Gmail (one browser click)

The bot needs to read your Gmail inbox to find job alert emails. Run:
```bash
python3 setup_oauth.py
```

A browser window will open automatically. Log in with **your Gmail account** and click **Allow**. That's it — you'll never have to do this again.

---

### Step 3 — Set your job preferences

Run the setup wizard (includes filters — location, salary, titles, deal-breakers):
```bash
cd ~/shortlistr/automation
python3 setup.py
```

To change filters later, edit `config/profile.yml` or re-run `python3 setup.py`.

To check current filters, open `config/profile.yml` under the `filters:` section.

### Discovery without adding every company

Greenhouse, Lever, and Ashby APIs are **per-company** — there is no global “search all jobs” endpoint. shortlistr uses a **hybrid** model instead:

1. **Keyword aggregators** (Himalayas, RemoteOK, Remotive, LinkedIn) — driven by `filters.target_titles` in `config/profile.yml`
2. **`portals.yml` `search_queries`** — cross-company discovery via `site:job-boards.greenhouse.io "DevOps"` (runs in `make scan` and daily cron)
3. **`tracked_companies`** — optional watchlist for employers you always want checked
4. **Paste any ATS job URL** — resolves without adding the company to a list:

```bash
python3 -m automation.cli resolve-url "https://job-boards.greenhouse.io/vercel/jobs/123456"
```

Optional search API keys in `.env` (better Level 3 results than free DuckDuckGo):

```
GOOGLE_CSE_API_KEY=...
GOOGLE_CSE_CX=...
# or
SERPAPI_KEY=...
```

---

## ☀️ PART 2 — Every Morning (your daily 5-minute routine)

### The bot already ran at 9 AM automatically

You don't press anything. The bot woke up, searched 20+ job sites, filtered the results, and left you a neat review file.

---

### Step 4 — Check what the bot found

Open this file in any text editor (TextEdit, VS Code, Obsidian):
```
Documents → shortlistr → shortlistr → data → apply_queue.md
```

Or open it from Terminal:
```bash
open ~/shortlistr/data/apply_queue.md
```

You'll see something like this for each job:

```
### 1. Datadog — Senior SRE
**Decision:** `PENDING` ← change to YES / NO / SKIP
Score: 80 | Remote | $100k–$120k
URL: https://boards.greenhouse.io/datadog/jobs/...
```

---

### Step 5 — Review jobs interactively (one keypress per job)

Run this in Terminal:
```bash
cd ~/shortlistr/automation
python3 processors/review_queue.py
```

Each job appears on screen one at a time. Just press **one key**:

```
  Company   Datadog
  Title     Senior SRE
  Score     80/100
  Salary    $100k–$120k
  Source    Remotive
  Location  Remote

  [Y] Apply   [N] Skip   [S] Later   [O] Open in browser   [Q] Quit
```

- **Y** → Yes, apply to this
- **N** → Not interested
- **S** → Maybe later, keep it
- **O** → Opens the job URL in your browser so you can read the full description, then press Y/N/S
- **Q** → Quit and save progress (you can continue later)

At the end it asks if you want to submit your YES jobs immediately. Press **Y** and it's done.

---

### Step 6 — Check your generated CV PDFs and interview prep

When you press **Y** at the "submit?" prompt, the bot automatically generates two things:

**1. A branded CV PDF** for each company — saved to `output/`:
```bash
open ~/shortlistr/output/
```
Files look like: `datadog-2026-06-27.pdf`, `grafana-labs-2026-06-27.pdf`
These are your master CV in the branded template — ready to attach.

> If PDF generation fails (Node/Playwright not installed), the bot logs a warning and continues. Generate manually anytime:
> ```bash
> cd ~/shortlistr/automation
> python3 processors/generate_cv.py --company "Datadog"
> ```

**2. An interview prep file** for each job — saved to `interview-prep/`:
```bash
open ~/shortlistr/interview-prep/
```
Files look like: `datadog-senior-site-reliability-engineer.md`

Each prep file contains:
- Skills to emphasise (extracted from the JD match)
- Your proof points from cv.md (quantified achievements)
- 10 role-specific technical questions with blank STAR+R slots
- 10 behavioral questions with blank STAR+R slots
- Company research checklist (fill in the night before)
- Smart questions to ask the interviewer

Open in VS Code, Obsidian, or any markdown editor. Fill in your answers before the interview.

> **Tip:** When you evaluate a job via `/shortlistr evaluate` or `/shortlistr {JD}`, the AI layer adds STAR+R stories to `interview-prep/story-bank.md`. These flow into future prep files automatically.

---

### Step 7 — Check for recruiter messages

If any recruiter emailed you directly, the bot already drafted a reply. Open:
```
Documents → shortlistr → shortlistr → data → recruiter_drafts.md
```

Or:
```bash
open ~/shortlistr/data/recruiter_drafts.md
```

Read the draft, copy it, paste it into your email, make any tweaks, and send. The bot writes it — you just press Send.

---

## 🧪 PART 3 — Test it without sending anything

Whenever you want to see what the bot *would* do without actually doing it:
```bash
cd ~/shortlistr/automation
python3 run_daily.py --dry-run
```

It runs everything but sends nothing and applies to nothing. Safe to run anytime.

---

## 📊 PART 4 — Check your application tracker

The bot logs every job it finds in a spreadsheet:
```
Documents → shortlistr → shortlistr → automation → data → Job_Application_Tracker.xlsx
```

Open it in Excel or Numbers. It shows every job, its score, source, whether you applied, and the status.

---

## 🚨 PART 5 — Something went wrong?

### The bot didn't run today

Check the log:
```bash
cat ~/shortlistr/automation/logs/cron.log | tail -50
```

Or run it manually right now:
```bash
cd ~/shortlistr/automation
python3 run_daily.py
```

### Queue is empty (no jobs found)

That means the bot ran but everything it found was filtered out (on-site, low salary, wrong title). This is correct — the filters are working. Try again tomorrow or loosen filters in `config/profile.yml` or re-run:
```bash
cd ~/shortlistr/automation && python3 setup.py
```

### Check what's in the queue right now

```bash
python3 ~/shortlistr/automation/processors/apply_queue.py --status
```

---

## 📋 Cheat Sheet — Commands you'll actually use

| What you want | Command |
|---------------|---------|
| See current filters | `cat ~/shortlistr/config/profile.yml` |
| Change filters | `cd ~/shortlistr/automation && python3 setup.py` |
| Run the bot NOW (live) | `cd ~/shortlistr/automation && python3 run_daily.py` |
| Run the bot (safe preview) | `cd ~/shortlistr/automation && python3 run_daily.py --dry-run` |
| Review jobs interactively (one keypress) | `cd ~/shortlistr/automation && python3 processors/review_queue.py` |
| Check queue status | `cd ~/shortlistr/automation && python3 processors/apply_queue.py --status` |
| Generate CV PDF manually | `cd ~/shortlistr/automation && python3 processors/generate_cv.py --company "Datadog"` |
| Generate all interview prep files | `cd ~/shortlistr/automation && python3 processors/generate_prep.py` |
| See CV PDFs | `open ~/shortlistr/output/` |
| See interview prep files | `open ~/shortlistr/interview-prep/` |
| See recruiter drafts | `open ~/shortlistr/data/recruiter_drafts.md` |
| See recent log | `tail -50 ~/shortlistr/automation/logs/cron.log` |
| Resolve a pasted ATS job URL | `python3 -m automation.cli resolve-url "<url>"` |
| Scan portals + keyword search | `make scan` or `make scan ARGS="--dry-run"` |
| System status (last run, sources) | `make status` |
| Import pipeline.md → SQLite | `make migrate-markdown` |
| Export SQLite → pipeline.md | `make export-pipeline` |
| Evaluate a job URL | `make evaluate ARGS="URL=https://..."` |
| Backup .shortlistr bundle | `make bundle ARGS="export"` |
| Local API + web inbox | `make api` then open http://127.0.0.1:8787/inbox |

---

## 🕐 What happens every day (automatically)

```
9:00 AM  → Bot wakes up
9:01 AM  → Checks your Gmail inbox for job alert emails
9:02 AM  → Searches 20+ job portals
9:05 AM  → Filters: removes on-site, low salary, wrong titles
9:06 AM  → Saves good jobs to apply_queue.md
9:07 AM  → Drafts replies to any recruiter emails
9:08 AM  → Bot goes back to sleep

YOUR TURN (whenever you wake up):
         → Run: python3 processors/review_queue.py
         → Press Y / N / S for each job
         → Press Y to submit at the end
         → Bot auto-generates CV PDFs → output/
         → Bot auto-generates interview prep → interview-prep/
         → Done in 2 minutes
```

---

*If you're stuck, ask your AI assistant to walk you through the daily automation flow.*
