# Security

Shortlistr is a **local-first** tool. There is no hosted multi-tenant service in this
repository. Still, bugs in path handling, scrapers, PDF generation, or secret
storage can put a user’s machine and credentials at risk.

## Scope

In scope:

- `automation/` — path traversal, command injection, credential handling
- Apply-assist / Playwright flows — must never auto-submit
- `templates/` used for résumé HTML/PDF — XSS in generated documents
- Dashboard API on `127.0.0.1` — auth assumptions if LAN exposure is enabled

Out of scope:

- Abuse of third-party job boards (LinkedIn, Naukri, Apify, ATS sites) via
  scrapers you enable — that is a ToS/user-responsibility issue
- Secrets you put in a committed `.env` or paste into a public issue

## Reporting a vulnerability

Please **do not** open a public GitHub issue for security bugs.

Prefer one of:

1. **GitHub Security Advisories** — on the repo, use *Security → Advisories →
   Report a vulnerability* (private to maintainers)
2. A private email / maintainers contact if Advisories are unavailable

Include: affected version/commit, reproduction steps, impact, and (if possible)
a minimal patch idea. We will acknowledge reports and work on a fix before any
public disclosure.

## Secret hygiene

Never commit:

- `.env`, API keys, Gmail OAuth tokens
- `cv.md`, `config/profile.yml`, `portals.yml`, `data/shortlistr.db`
- Real phone numbers, résumés, or employer confidential JDs

If you accidentally push a secret, rotate it immediately and open a private
advisory so maintainers can purge history if needed.
