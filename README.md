# Shortlistr

**Local-first job search on your laptop** — discover roles, score fit, prepare materials, and prefill applications. **You** always click Submit.

Product site: [shortlistr.xyz](https://shortlistr.xyz)

No cloud account. No phone-home. Your CV, profile, and job tracker stay in files on your machine.

```
Discover → Evaluate → Approve → Prep → Prefill → You click Submit
```

---

## What it is / isn’t

| It is | It is not |
|-------|-----------|
| A personal job-search pipeline on your laptop | A mass-apply bot |
| Discover + score + prep + form **prefill** | Auto-submit to LinkedIn, Naukri, or ATS forms |
| Optional Local AI / API keys / Apify | A hosted SaaS |
| MIT-licensed open source | Permission to violate third-party Terms of Service |

---

## Requirements

| Tool | Version | Notes |
|------|---------|-------|
| Python | 3.10+ | Required up front (`python -m automation.cli start`) |
| Node.js | 18+ | **Auto-installed** by `make start` if missing |
| Playwright Chromium | — | Installed by `make start` |

---

## Quick start

```bash
git clone https://github.com/sarojgn810/shortlistr.git
cd shortlistr
python -m automation.cli start
```

| Platform | Same thing |
|----------|------------|
| macOS / Linux | `make start` |
| Windows | double-click `start.bat`, or `.\start.ps1` |

**What `start` does**

1. Checks **Python 3.10+** (must already be installed — you are running it)
2. **Installs Node.js automatically** if missing (Homebrew / winget, or a portable copy under `.tools/`)
3. Installs Python packages, Playwright Chromium, and dashboard deps
4. Seeds local placeholders (`cv.md`, `portals.yml`, `.env`, SQLite)
5. Starts API (`http://127.0.0.1:8787`) and dashboard (`http://localhost:3000`)
6. Opens **http://localhost:3000/onboarding**

Then finish the wizard: upload résumé → confirm titles/locations → scan.

Day-to-day setup (LLM key, Playwright, Apify, Gmail) lives in the dashboard **Connections** page — not in hand-edited shell commands.

---

## YC demo script (≈5 minutes)

Happy path for a live demo on a second laptop:

1. **Install** — `python -m automation.cli start` (or `make start` / `start.bat`)
2. **Onboarding** — upload CV → confirm target titles + locations → Finish
3. **AI** — open **Connections** → paste a free [Groq API key](https://console.groq.com/keys) (or Set up Local AI). Hybrid `auto` prefers Local when ready; Groq is the fastest demo path.
4. **Discover** — open Discover → Scan → wait for inbox cards (list stays slim — no full eval JSON blobs)
5. **Approve** — Approve or Skip (optimistic UI; you always click Submit later)
6. **Prep** — open an approved role → Prep for cover letter / reach-out (never auto-sent)

Without an AI key, chat still answers basic commands (`status`, `inbox`, `discover`) and shows a clear CTA to Connections — it never fails silently.

---

## How the pipeline works

```
Setup → Discover → Evaluate → Approve → Prep → Apply assist → You Submit
```

1. **Discover** — company watchlist (`portals.yml`), Workday, aggregators, LinkedIn guest, Gmail job alerts, optional Naukri/Apify  
2. **Filter** — only roles matching your preferred titles and locations (e.g. Bangalore + Remote India, not worldwide remote)  
3. **Evaluate** — CV vs JD (LLM or heuristic)  
4. **Approve** — you choose what is worth applying to  
5. **Prep** — cover letter / interview notes  
6. **Apply assist** — prefill the form in a browser; **you** click Submit  

Add employers in `portals.yml` (start from `templates/portals.example.yml`). Keep it a short personal watchlist.

---

## Privacy

| Stays on your disk (gitignored) | Never sent to us |
|--------------------------------|------------------|
| `cv.md`, `config/profile.yml`, `.env` | No telemetry |
| `portals.yml`, `data/shortlistr.db` | No outbound account |
| `reports/`, `output/`, `interview-prep/` | Secrets via `.env` / OS keychain only |

A fresh clone has **placeholders only**. Do not commit résumés, phone numbers, or API keys.

---

## Legal & ethics

**You** must comply with the Terms of Service of LinkedIn, Naukri, Indeed, Apify, Greenhouse, Lever, and every employer ATS you use.

- Scrapers and Apify are **opt-in** and at **your own risk**. Prefer careers pages in `portals.yml` and public ATS APIs when you can.
- MIT licenses **this code** — not a license to break site ToS or the law.
- Shortlistr **never auto-submits**. Prefer fit ≥ 4.0/5 before applying.

---

## Common commands

```bash
make start                 # install + seed + run + open /onboarding
make dev                   # start API + scheduler + dashboard (already installed)
make doctor                # environment check
make test                  # pytest
make scan                  # run discovery once
make reset                 # wipe job data / profile to a blank slate (keeps .env)
make uninstall             # remove Shortlistr from this machine (see below)
make uninstall ARGS=--purge-data   # uninstall + delete résumé, DB, .env, etc.
```

| Goal | Command |
|------|---------|
| Use Shortlistr again tomorrow | `make dev` (or leave the stack running) |
| Clear jobs and re-onboard | `make reset` |
| Remove Shortlistr completely | `make uninstall`, then delete the folder |

---

## Uninstall / remove Shortlistr

Use this when you want Shortlistr **off the machine**, not just a blank profile.

### 1. Guided cleanup (from the project folder)

```bash
# Stops local servers, removes cron hooks, clears keychain secrets,
# and removes node_modules / build caches. Prints final steps.
make uninstall

# Same, and also permanently deletes résumé, profile, DB, .env, portals.yml,
# and reset backups (cannot undo):
make uninstall ARGS=--purge-data
```

Windows (PowerShell):

```powershell
python -m automation.cli uninstall
python -m automation.cli uninstall --purge-data
```

### 2. Delete the project folder

`make uninstall` does **not** delete the repository directory. Remove it yourself:

```bash
# macOS / Linux — from the PARENT of the clone
cd ..
rm -rf shortlistr        # use your actual folder name
```

```powershell
# Windows — from the parent folder
Remove-Item -Recurse -Force .\shortlistr
```

### 3. Optional extras

Only if you installed these for Shortlistr:

```bash
# Playwright Chromium browser cache
python3 -m playwright uninstall chromium

# Local AI models (Ollama)
ollama list
ollama rm <model-name>

# Python packages from this project (run before deleting the folder)
pip3 uninstall -y -r automation/requirements.txt
```

System Python and Node can stay — Shortlistr does not require uninstalling them.

### What is removed vs kept

| Removed by `make uninstall` | Kept until you delete the folder | Optional / manual |
|-----------------------------|----------------------------------|-------------------|
| Processes on `:3000` / `:8787` | Source code + templates | Playwright Chromium cache |
| Crontab lines for this app | `cv.md`, profile, DB (unless `--purge-data`) | Ollama models |
| OS keychain secrets | `.env` / `portals.yml` (unless `--purge-data`) | System Python / Node |
| `node_modules` / build caches | | |

More detail: [GETTING_STARTED.md §7](GETTING_STARTED.md#7-uninstall--remove-autojob-completely).

---

## Optional extras

- **Local AI** — Connections can install a small on-device model (no cloud key). Cloud LLM keys remain optional for richer evaluations.
- **Gmail** — ingest job-alert emails (read + unread, last 7 days) from Connections.
- **Apify** — optional paid board scrapers; free credit is often enough for personal use.
- **Company watchlist** — edit `portals.yml` for careers URLs you care about.

---

## Docs

| Doc | Contents |
|-----|----------|
| [GETTING_STARTED.md](GETTING_STARTED.md) | First run, reset, uninstall |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Stack and data flow |
| [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) | PRs, tests, no personal data |
| [AGENTS.md](AGENTS.md) | Rules for AI assistants in this repo |
| [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) | Contributor Covenant |
| [SECURITY.md](SECURITY.md) | Vulnerability reports |
| [LICENSE](LICENSE) | MIT |

---

## License

MIT — see [LICENSE](LICENSE).

MIT does **not** grant rights under LinkedIn, Naukri, Apify, or employer Terms of Service. Use ethically; never auto-submit.

---

## Author

Built by [sarojnayak.com](https://www.sarojnayak.com)
