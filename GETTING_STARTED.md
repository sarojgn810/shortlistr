# Getting Started with shortlistr

A local-first, judgment-first job search copilot. It finds roles, scores them
honestly, helps you prep and fill applications — and **you** click submit. Your
data stays on your machine.

This guide takes you from a fresh clone to your first reviewed job.

---

## 1. Install (one time)

```bash
make install          # Python deps + Playwright/Chromium (used for PDF + form-fill)
make dashboard-install # dashboard (Next.js) deps
```

You need Python 3.10+ and Node 18+. No LaTeX/MacTeX required — PDFs render through
Chromium.

---

## 2. Start the app

One command on **any OS** — installs deps, seeds files, runs API + dashboard + scheduler,
opens onboarding:

```bash
python -m automation.cli start
```

- **Windows:** you can also double-click **`start.bat`** or run **`.\start.ps1`**.
- **macOS/Linux:** `make start` works too (it calls the same launcher).

Already installed? Skip installing with `python -m automation.cli dev` (or `make dev`).

Or run the pieces yourself:

```bash
python -m automation.cli api        # backend API on http://127.0.0.1:8787
npm --prefix dashboard run dev      # dashboard on http://localhost:3000
```

Open **http://localhost:3000/onboarding**.

---

## 3. Onboarding (first run)

The wizard walks five steps. It only appears until you finish it; after that
`/onboarding` sends you to your dashboard.

1. **Profile** — name, contact, target titles, work mode, salary floor, and your
   LLM choice. Saved to `config/profile.yml` (API keys go to your OS keychain, never
   the YAML).
2. **Resume** — upload your PDF or Word file (or paste markdown). The text is
   extracted to `cv.md` for matching, and your original PDF is kept as-is.
3. **Template** — pick an ATS-safe layout; preview renders live at A4.
4. **Review** — see your setup checklist and resume, enable scheduled discovery.
5. **Done** — jump to Discover, or manage anything later from the sidebar.

---

## 4. The daily loop

```
Discover → review & evaluate → approve → prep → apply assist → YOU submit
```

| Where | What you do |
|-------|-------------|
| **Today** (`/dashboard`) | See what needs action: new jobs, approved, active. |
| **Discover** (`/inbox`) | Run discovery, evaluate jobs, approve or skip. Toggle **Relevant / All** to widen what you see. |
| **Pipeline** (`/pipeline`) | Track everything: Review → Approved → Applied → Active. |
| **Resume** (`/cv`) | Edit your resume, switch templates, download PDF, choose which resume applications send. |
| **Profile** (`/profile`) | Personal info, job targeting, and auto-fill answers. |
| **Connections** (`/connections`) | LLM, job sources, platforms, email, messaging, MCP. |
| **Settings** (`/settings`) | Scheduler, scoring thresholds, data export. |

---

## 5. Key choices

**Which resume gets sent?** On **Resume** (`/cv`), pick:
- **My uploaded PDF** (default) — applications attach your original file, untouched.
- **Generated template** — applications attach a tailored template PDF per job.

**LLM is optional.** With a key set in **Connections**, you get full A–G evaluation
and cover letters. Without one, the app runs in **template mode** (keyword scoring)
so everything still works.

**Discovery breadth.** Discover persists every job it finds. The inbox shows
**Relevant** matches by default; switch to **All** to see off-target finds and
decide for yourself. Add or remove tracked companies and sources in `portals.yml`.

---

## 6. Start over (blank slate)

```bash
make reset            # wipes jobs, resume, profile, generated output -> backup
```

Your current data is copied to `.reset-backup/<timestamp>/` first. Your secrets
(`.env` / keychain) and `portals.yml` are preserved. Then run `make start` and
onboard fresh.

---

## 7. Uninstall / remove Shortlistr completely

Use this when you want Shortlistr **off the machine**, not just a blank profile.

### Guided cleanup (recommended)

From the project folder:

```bash
# Stop local servers, remove cron hooks, clear Shortlistr keychain secrets,
# and remove node_modules / build caches. Then prints the final steps.
make uninstall

# Same, but also delete résumé, profile, DB, .env, portals.yml, and backups
# (cannot undo — only do this if you do not need that data):
make uninstall ARGS=--purge-data
```

Windows (PowerShell), from the project folder:

```powershell
python -m automation.cli uninstall
python -m automation.cli uninstall --purge-data
```

### Final step — delete the app folder

After `make uninstall` finishes, remove the repository itself:

```bash
# macOS / Linux — run from the PARENT of the project folder
cd ..
rm -rf shortlistr    # or whatever you named the clone
```

```powershell
# Windows — from the parent folder
Remove-Item -Recurse -Force .\shortlistr
```

### Optional extras (only if you installed them for Shortlistr)

```bash
# Playwright Chromium (shared browser cache)
python3 -m playwright uninstall chromium

# Cron jobs (if you ever ran the ingest cron installer)
bash scripts/setup-job-crons.sh --remove

# Local AI models pulled via Ollama (list first, then remove what you want)
ollama list
ollama rm <model-name>
```

Python / Node themselves can stay — Shortlistr does not require uninstalling them.
Pip packages from `automation/requirements.txt` are optional to remove:

```bash
pip3 uninstall -y -r automation/requirements.txt
```

(Run that **before** deleting the folder, or keep a copy of `requirements.txt`.)

### What gets removed vs kept

| Removed by `make uninstall` | Kept until you delete the folder | Optional / manual |
|-----------------------------|----------------------------------|-------------------|
| Processes on `:3000` / `:8787` | Code + templates | Playwright Chromium cache |
| Shortlistr crontab lines | `cv.md`, profile, DB (unless `--purge-data`) | Ollama models |
| OS keychain secrets (`shortlistr` service) | `.env` / `portals.yml` (unless `--purge-data`) | System Python / Node |
| `dashboard/node_modules`, `.next` | | |

Nothing is uploaded. After you delete the folder, Shortlistr is gone.

---

## 8. Troubleshooting

| Symptom | Fix |
|---------|-----|
| Dashboard loads but data is empty | Start the API: `make api`. |
| PDF won't download | Open **Connections** and install Playwright, then regenerate. |
| Evaluations say "template mode" | Add an LLM key in **Connections**, then re-evaluate. |
| Apply-assist can't find the form | Open the posting, click Apply, then retry. |
| No jobs after discovery | Switch the inbox to **All**, or widen target titles in **Profile**. |

---

## Where things live

- `config/profile.yml` — your profile (gitignored).
- `cv.md` + `resume.pdf` — your resume content and original file (gitignored).
- `data/shortlistr.db` — local SQLite store for jobs, pipeline, applications.
- `portals.yml` — tracked companies and discovery sources.
- `.env` — secrets (or use the OS keychain).
- `output/` — generated resume PDFs.

Everything runs on your machine. Nothing is uploaded.
