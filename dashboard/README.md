# Shortlistr Dashboard

Judgment-first web UI for the shortlistr pipeline. Visual standards match the JobPilot reference (`docs/UI_DESIGN_STANDARDS.md`).

## Quick start

```bash
# From repo root
make api              # Terminal 1 — FastAPI on :8787
make dashboard-install
make dashboard-dev    # Terminal 2 — Next.js on :3000
```

Open [http://localhost:3000](http://localhost:3000).

## Configuration

Copy `.env.example` → `.env.local`:

| Variable | Default | Purpose |
|----------|---------|---------|
| `NEXT_PUBLIC_SHORTLISTR_API_URL` | `http://127.0.0.1:8787` | FastAPI base URL |
| `NEXT_PUBLIC_SHORTLISTR_API_TOKEN` | (empty) | Bearer token if `SHORTLISTR_API_TOKEN` is set |
| `NEXT_PUBLIC_ENABLE_MOCK` | `false` | Force mock data |

If the API is unreachable, the UI falls back to sample data with a warning.

## Routes

| Path | Purpose |
|------|---------|
| `/dashboard` | Overview stats |
| `/inbox` | Pending jobs + evaluate |
| `/tracker` | Kanban pipeline |
| `/reports` | Linked evaluation reports |
| `/settings` | API connection info |

## Stack

Next.js 15 · React 19 · Tailwind 3 · Urbanist · Framer Motion · Lucide · Zustand · Sonner

## Next steps (J3)

- [ ] Render full eval blocks A–G in job detail modal
- [ ] Approve / skip actions → SQLite status updates
- [ ] Résumé diff modal before approve
- [ ] Application receipts drawer after submit
