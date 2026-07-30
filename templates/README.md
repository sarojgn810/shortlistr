# Templates

| File | Used by | Purpose |
|------|---------|---------|
| `cv-template.html` | `automation/generate_pdf.py` | ATS CV PDF (Playwright) |
| `portals.example.yml` | Onboarding | Example portal config → copy to `portals.yml` |
| `states.yml` | Tracker scripts | Canonical application statuses |

**cv-template.html** uses placeholders (`{{NAME}}`, `{{EXPERIENCE}}`, etc.) filled at PDF generation time. Fonts live in `fonts/`.

**states.yml** defines: `Evaluated`, `Applied`, `Responded`, `Interview`, `Offer`, `Rejected`, `Discarded`, `SKIP`. Do not rename state IDs.
