# UI design standards (JobPilot reference)

**Reference implementation:** JobPilot dashboard at `AI JobPilot/UI_Antigravity/jobpilot-dashboard` (local path on author machine).

Use this folder as the **visual and component source of truth** when building shortlistr web UI (Phase J3). Do not invent a new design system — extend or port JobPilot patterns.

Related: [COMPETITIVE_POSITIONING.md](COMPETITIVE_POSITIONING.md)

---

## Stack (match reference)

| Layer | Choice |
|-------|--------|
| Framework | Next.js 16 App Router |
| Styling | Tailwind CSS 3.4 |
| Font | **Urbanist** (`next/font/google`) |
| Icons | `lucide-react` |
| Motion | `framer-motion` (Kanban, modals) |
| Charts | `recharts` (dashboard widgets) |
| Forms | `react-hook-form` + `zod` |
| State | `zustand` |
| Toasts | `sonner` |
| Utils | `clsx` + `tailwind-merge` → `cn()` |

Reference: `package.json`, `app/layout.tsx`, `src/lib/utils/cn.ts`

---

## Design tokens

From `app/globals.css` and `tailwind.config.js`:

| Token | CSS variable | Hex | Usage |
|-------|--------------|-----|--------|
| **sage** | `--bg-sage` | `#F3F6F2` | Page background |
| **mist** | `--surface-mist` | `#ECEFE9` | Borders, subtle fills, column headers |
| **lime** | `--accent-lime` | `#DFFF5E` | Primary accent, match badges, CTAs |
| **orange** | `--accent-orange` | `#FF6B4A` | Alerts, secondary accent |
| **ink** | `--text-ink` | `#1A1A1A` | Primary text |
| **stone** | `--text-stone` | `#666666` | Secondary text, metadata |

### Typography

- Font: **Urbanist**, `antialiased`, `tracking-tight` on dashboard shells
- Labels/metadata: `text-xs font-bold uppercase tracking-widest text-stone`
- Headings: `font-bold text-ink`
- Body default: `text-base text-ink`

### Radius (signature look)

| Element | Radius |
|---------|--------|
| Cards (main) | `rounded-[28px]` – `rounded-[32px]` |
| Kanban columns | `rounded-[40px]` |
| Buttons (md/lg) | `rounded-2xl` |
| Buttons (sm) | `rounded-xl` |
| Badges | `rounded-full` |

Large corner radius is **intentional** — keep it consistent.

### Shadows & interaction

- Cards: `shadow-sm` default → `hover:shadow-xl` on job cards
- Primary button: `bg-black text-lime shadow-xl shadow-black/10 hover:scale-[1.02] active:scale-95`
- Lime CTA variant: `bg-lime text-black`
- Glass cards: `bg-white/60 backdrop-blur-xl border border-white/50`

---

## Layout patterns

### Dashboard shell

Reference: `src/components/layout/DashboardShell.tsx`

```text
┌──────────┬─────────────────────────────────────┐
│ Sidebar  │ TopBar (title, breadcrumbs)         │
│ (fixed)  ├─────────────────────────────────────┤
│          │ Main content (scroll)               │
│          │                                     │
└──────────┴─────────────────────────────────────┘
```

- `min-h-screen bg-sage text-ink font-sans flex tracking-tight`
- Content: `md:pl-24` (sidebar offset), `custom-scrollbar` on overflow
- Mobile: bottom padding `pb-28` for nav clearance

### Setup pages (Profile, Connections, Settings)

- The page container is `w-full`, never `max-w-*`. These pages were pinned to
  `max-w-2xl`, which left roughly half the window empty on a laptop.
- Cards span that full width; **the forms inside do not**. Inputs get
  `max-w-2xl`/`max-w-3xl` or sit in a `sm:grid-cols-2` / `xl:grid-cols-3` grid,
  because a single text box 1200px wide is worse to fill in than a narrow one.
- Read-only values stack **label above value** in a multi-column grid, not
  label-left / value-flush-right. At full width the right-flush version put a
  phone number a thousand pixels from the word "Phone".
- Type scale on these pages: body `text-base`, labels and hints `text-sm`,
  section headings `text-lg`. `text-xs` is for chips and badges only — it is
  too small for anything a user has to read to complete setup.

### All dashboard pages (same type + width rules)

Apply the same scale everywhere the shell wraps content — Today, Discover,
Pipeline, Apply, Reports, Resume, Prep, Chat, Onboarding — and to shared
pieces (`JobCard`, `JobRow`, `JobDetailModal`, `CvWorkspace`, sidebar, TopBar).
Page wrappers are `w-full`. Conversation and apply-runner cards may keep a
`max-w-3xl` *inside* the full-width page so a single form stays readable; the
page itself must not leave a dead right column.

### Sidebar

Reference: `src/components/layout/Sidebar.tsx`

- Icon-only rail on desktop; role-based nav (user / employer / admin)
- Active item: filled icon + lime/black accent dot
- User role default: `bg-black` accent on active

### TopBar

Reference: `src/components/layout/TopBar.tsx`

- Page title + breadcrumb trail
- Optional **focus mode** toggle: `Hunter` | `Grower` (user dashboard)

---

## Component library (port these)

Location: `src/components/ui/`

| Component | Variants | Notes |
|-----------|----------|-------|
| `Button` | primary, secondary, ghost, danger, **lime** | Black+lime = default primary |
| `Card` | default, elevated, outline, **glass** | `rounded-[32px]` |
| `Badge` | default, lime, orange, success, warning, error | Match % uses black+lime badge on cards |
| `Modal` | — | Job detail, settings |
| `Input` | — | Forms |
| `Skeleton` | — | Loading states |
| `Toast` | via sonner | |

Use `cn()` for class merging — never raw string concat.

---

## User-facing screens to mirror for shortlistr

Map JobPilot **user** routes → shortlistr **judgment-first** flows:

| JobPilot route | Component | Shortlistr equivalent |
|----------------|-----------|-------------------|
| `/user/jobs` | `JobCard`, filters, `JobDetailModal` | **Inbox** — pending jobs with eval score + legitimacy |
| `/user/tracker` | `KanbanBoard` | **Tracker** — pipeline columns (see status mapping below) |
| `/user/dashboard` | Widget grid | **Dashboard** — run stats, pending count, recent evals |
| `/user/resumes` | Resume list | **CV / prep** — tailored PDFs per role |
| `/user/coach` | Chat coach | Optional later (IDE skill covers much of this) |
| `/user/interviews` | Interview list | **Interview prep** — link to `interview-prep/` reports |

### JobCard pattern (adapt for shortlistr)

Reference: `src/components/user/JobCard.tsx`

- White card, `rounded-[28px]`, border `border-mist/30`
- **Match badge** top-right: `bg-black text-lime` with sparkle icon
- Company initial / logo in `rounded-2xl` black square
- Metadata row: company · location · type (uppercase tracking-widest)

**Shortlistr adaptation:** Replace generic `matchScore %` with:
- Eval score `X.X/5` (primary)
- Legitimacy tier badge (verified / uncertain / suspicious)
- One-line “why matched” from `fit_reason` or eval explainer

### Kanban pattern (adapt for shortlistr)

Reference: `src/components/user/KanbanBoard.tsx`

JobPilot columns: **Wishlist → Applied → Interview → Offer**

Shortlistr judgment-first columns (proposed):

| Column | Statuses | Color accent |
|--------|----------|--------------|
| **Pending** | `pending`, `evaluated` | `bg-mist` |
| **Approved** | ready to apply | `bg-blue-100/50` |
| **Submitted** | `applied` | `bg-lime/20` |
| **Active** | `responded`, `interview`, `offer` | `bg-green-100/50` |

Use same column chrome: rounded `[40px]` container, count pill, `framer-motion` for card enter/exit.

---

## Shortlistr-specific UI rules (differentiate from Tsenta)

JobPilot skews toward **match % + auto-apply**. Shortlistr UI must emphasize **judgment**:

1. **Score before action** — eval score and legitimacy visible on every card; no “Apply” without opening eval summary.
2. **Approve step** — explicit button (lime primary) between prep and submit; show résumé diff modal before approve.
3. **Receipt drawer** — after submit, slide-over with fields sent (Tsenta parity, our ethics).
4. **No volume counters** — do not show “600 applications left”; show “12 pending review” instead.
5. **Reports link** — each job links to `reports/{###}-*.md` or in-app eval blocks A–G.

---

## API wiring (when UI is built)

Shortlistr backend today:

| UI need | Source |
|---------|--------|
| Pending jobs | `GET /jobs?status=pending` or SQLite via FastAPI |
| Evaluate | `POST /jobs/{id}/evaluate` |
| Discover | `POST /jobs/discover` |
| Tracker | `GET /applications` + SQLite `applications` |
| Local dev | `make api` → `http://127.0.0.1:8787` |

JobPilot uses `src/lib/api/client.ts` + mocks — shortlistr UI can follow same hook pattern (`useJobs` → `usePipeline`).

**Recommended:** New app at `shortlistr/dashboard/` (or monorepo subfolder) copying JobPilot shell, pointing hooks at shortlistr FastAPI instead of Supabase mocks.

---

## File map (quick reference)

```text
jobpilot-dashboard/
├── app/
│   ├── globals.css          # CSS variables
│   ├── layout.tsx           # Urbanist, sage bg
│   └── user/
│       ├── jobs/page.tsx      # Job feed
│       ├── tracker/page.tsx   # Kanban
│       └── dashboard/page.tsx
├── tailwind.config.js       # sage, mist, lime, ink, stone
└── src/
    ├── components/
    │   ├── layout/          # DashboardShell, Sidebar, TopBar
    │   ├── ui/              # Button, Card, Badge, Modal…
    │   └── user/            # JobCard, KanbanBoard, widgets
    ├── hooks/               # useJobs, useApplications
    └── config/navigation.ts
```

---

## Implementation checklist (J3)

When starting UI work:

- [x] Copy design tokens (`globals.css`, `tailwind.config.js`) into `dashboard/`
- [x] Port `src/components/ui/*` and `cn()` utility
- [x] Port `DashboardShell` + `Sidebar` with shortlistr nav: Inbox · Tracker · Reports · Settings
- [x] Scaffold **Inbox** page using `JobCard` pattern + eval badges
- [x] Scaffold **Tracker** using `KanbanBoard` pattern + shortlistr statuses
- [ ] Build **Job detail** modal: full eval blocks A–G + approve / skip actions
- [x] Wire hooks to `automation/api/main.py` (CORS enabled for :3000)
- [x] Keep `make export-pipeline` / IDE flow working in parallel

---

## Document history

| Date | Change |
|------|--------|
| 2026-06 | Initial standards doc referencing JobPilot dashboard path |
