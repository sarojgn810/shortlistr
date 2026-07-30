# Project memory

Durable, human-readable memory for Shortlistr so any session — a new chat, a new model,
a teammate — can **pick up where the last one left off**. Plain markdown on purpose:
no service to run, every agent can read it, it diffs in git.

This implements the **retrieve → generate → store** loop from
[WORKFLOW.md](../../WORKFLOW.md).

## The three memory types

| Type | File | Holds |
|------|------|-------|
| **Semantic** (facts/specs/decisions) | [decisions.md](decisions.md) | Stable truths about how the system works and why — architecture decisions, conventions, "we chose X over Y because…". |
| **Episodic** (what happened) | [incidents.md](incidents.md) | Concrete runs that taught us something — bugs, root causes, the fix, the tests/logs. Dated, append-only. |
| **Procedural** (rules/workflows) | [CLAUDE.md](../../CLAUDE.md) + [WORKFLOW.md](../../WORKFLOW.md) | How we work and the landmines to avoid. Lives in the always-loaded docs, not here. |

## The loop

1. **Retrieve** — at session start, skim `decisions.md` + `incidents.md` for anything
   touching today's task (search by feature/file/keyword).
2. **Generate** — fold the relevant entries into your plan/spec before coding.
3. **Store** — after a meaningful fix or decision, append an entry. Keep it short and
   structured (see the templates in each file).

## Hygiene & governance (what becomes memory)

Not everything is memory. Be selective so retrieval stays useful.

- **Store:** durable decisions, stable patterns/conventions, recurring bugs + their root
  cause, hard-won gotchas, user preferences that affect the build.
- **Don't store:** routine run traces, one-off chatter, anything already obvious from the
  code or git history, secrets/keys, large logs (link or quote the key lines only).
- **Keep current:** if an entry becomes wrong, edit or strike it (note the date) — stale
  memory is worse than none. Entries are dated so old ones can be pruned.
- **One fact per entry**, newest at the top of each section.

## Upgrading to a memory engine (optional, later)

The markdown files are the source of truth and the fallback. If/when retrieval needs to
scale (semantic search across many entries, cross-project memory), layer an engine like
**Mem0** or **Memori** on top *without* removing the files:

1. Add the dep in the backend/tools layer (e.g. `pip install mem0ai`).
2. On session/tool startup, query the engine for `{project, task}` and write the top-K
   results into [CLAUDE.md](../../CLAUDE.md) or a `PROJECT_CONTEXT.md` before launching
   Claude Code (so the agent still just reads files).
3. After a run, write the same structured entry to **both** the engine and the markdown
   file (markdown stays the durable, reviewable record).
4. Add retention (TTL/cleanup) + a simple audit of what's read/written once it backs
   production agents.

Until then, the markdown loop is the system — it already gives us retrieve/generate/store.
