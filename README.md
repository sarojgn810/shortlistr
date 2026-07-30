# Shortlistr

**Local-first, free, judgment-first job search** — discover roles, evaluate fit, prep materials, and apply with intention. You always click Submit.

Product site: [shortlistr.xyz](https://shortlistr.xyz)

Runs entirely on your machine. No cloud account required. Your CV, profile, and tracker stay in files you control.

```
Discover → Evaluate → Approve → Prep → Prefill → You click Submit
```

---

## What it is / isn’t

| It is | It is not |
|-------|-----------|
| A personal job-search pipeline on your laptop | A mass-apply bot |
| Discover + score + prep + form **prefill** | Auto-submit to LinkedIn, Naukri, or ATS forms |
| Optional Local AI / API keys / Apify | A hosted SaaS or phone-home service |
| MIT-licensed open source | A license to violate third-party Terms of Service |

---

## Legal & ethics (read this)

**You** are responsible for complying with the Terms of Service of LinkedIn, Naukri, Indeed, Apify, Greenhouse, Lever, and every employer ATS you touch.

- Browser scrapers and Apify actors are **opt-in** and at **your own risk**. Prefer company careers pages (`portals.yml` watchlist) and public ATS APIs when you can.
- The MIT license grants rights to **this code**, not permission to break site ToS, robots.txt, or applicable law.
- Shortlistr **never auto-submits** applications. Apply-assist may fill fields; **you** review and click Submit.
- Discourage blasting low-fit roles — quality over volume.

---

## Quick start

```bash
git clone https://github.com/sarojgn810/shortlistr.git
cd shortlistr
python -m automation.cli start
```

On **Windows**, double-click `start.bat` or run `.\start.ps1`. On **macOS/Linux**, `make start` works the same.

It will:

1. Verify **Python 3.10+** and **Node 18+**
2. Install Python packages, Playwright Chromium, and dashboard deps
3. Seed local placeholders (`cv.md`, `portals.yml`, `.env`, SQLite) — targeting comes from **your** résumé
4. Start API (`:8787`), scheduler, and dashboard (`:3000`)
5. Open **http://localhost:3000/onboarding**

---

## Core loop

```
Setup → Inbox (Discover) → Evaluate → Approve → Prep → Apply assist → You Submit
```

Add employers you care about in `portals.yml` (copy from `templates/portals.example.yml`). Keep the list small — a personal watchlist, not a phone book.

---

## Privacy

| Stays on your disk (gitignored) | Never phone-home |
|--------------------------------|------------------|
| `cv.md`, `config/profile.yml`, `.env` | No telemetry |
| `portals.yml`, `data/shortlistr.db` | No outbound “account” |
| `reports/`, `output/`, `interview-prep/` | Secrets only via `.env` / OS keychain |

A fresh clone contains **placeholder** data only. Do not commit résumés, phone numbers, or API keys.

---

## Optional extras

- **Local AI** — Connections can install a small on-device model (no cloud key).
- **Apify** — optional job-board actors; free ~$5 credit is usually enough. Recommended, not required.
- **Company watchlist** — edit `portals.yml`.

---

## Common commands

```bash
make start               # install + seed + run + open /onboarding
make dev                 # API + scheduler + dashboard (no install)
make test                # pytest
make doctor              # environment check
make scan                # portal scanner
make apply-assist ARGS="JOB_ID=..."
```

Day-to-day setup belongs in the dashboard **Connections** page.

---

## Community

| Doc | Contents |
|-----|----------|
| [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) | PRs, tests, no personal data |
| [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) | Contributor Covenant |
| [SECURITY.md](SECURITY.md) | How to report vulnerabilities |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Stack and data flow |
| [LICENSE](LICENSE) | MIT |

---

## License

MIT — see [LICENSE](LICENSE).

MIT does **not** grant rights under LinkedIn, Naukri, Apify, or employer Terms of Service. Use ethically; never auto-submit.

---

## Author

[shortlistr.xyz](https://shortlistr.xyz)
