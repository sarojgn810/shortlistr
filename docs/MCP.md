# MCP / Agent API (J3.2)

HTTP endpoints mirror the tool contracts agents should use. A dedicated MCP stdio server can wrap these later.

**Base URL:** `http://127.0.0.1:8787` (see `make api`)

## List tools

```
GET /agent/tools
```

Returns `shortlistr.discover`, `shortlistr.evaluate`, `shortlistr.explain`, `shortlistr.queue_apply`, `shortlistr.apply_assist`, `shortlistr.resolve_jobs`.

## Tool mapping

| Tool | HTTP | Notes |
|------|------|-------|
| `shortlistr.discover` | `POST /agent/discover` | Body: `{"dry_run": true}` |
| `shortlistr.evaluate` | `POST /agent/evaluate` | Body: `{"job_id": "..."}` |
| `shortlistr.explain` | `GET /agent/explain/{job_id}` | |
| `shortlistr.queue_apply` | `POST /agent/queue-apply` | Approves only — **never submits** |
| `shortlistr.apply_assist` | `POST /agent/apply-assist` | Playwright fill; **stops before Submit** |
| `shortlistr.resolve_jobs` | `POST /agent/resolve-jobs` | Body: `{"limit": 50}` |

## Ethics

- `queue_apply` sets pipeline status to `approved` only.
- `apply_assist` never clicks Submit / Apply.
- Human must review every application.

## CLI equivalents

```bash
make evaluate URL=...
make explain JOB_ID=...
make resolve-jobs
make apply-assist JOB_ID=... --headed
```

Manifest source: `automation/mcp/manifest.py`
