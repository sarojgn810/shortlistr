"""Tool registry + permission gate for agent-invoked actions.

Every agent-callable capability (built-in today, MCP-connected third-party tools
later) declares a side-effect class:

    read   — no state change                     → always allowed
    write  — internal DB mutation, reversible     → allowed (audited)
    submit — external / irreversible side effect  → GATED (needs confirm or autopilot)

This generalizes shortlistr's "never auto-submit" ethic into one dispatch gate, so
when MCP tools can send email / post to Slack / submit applications, autonomy is
opt-in per tool rather than implicit.
"""

from __future__ import annotations

from dataclasses import dataclass, field

READ = "read"
WRITE = "write"
SUBMIT = "submit"


class PermissionDenied(Exception):
    """Raised when a side-effecting tool is invoked without authorization."""


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    side_effect: str = WRITE
    parameters: dict = field(default_factory=dict)
    http: dict | None = None

    def to_dict(self) -> dict:
        d = {
            "name": self.name,
            "description": self.description,
            "side_effect": self.side_effect,
            "parameters": self.parameters,
        }
        if self.http:
            d["http"] = self.http
        return d


_REGISTRY: dict[str, Tool] = {}


def register(tool: Tool) -> Tool:
    _REGISTRY[tool.name] = tool
    return tool


def get_tool(name: str) -> Tool | None:
    return _REGISTRY.get(name)


def list_tools() -> list[dict]:
    return [t.to_dict() for t in _REGISTRY.values()]


def _autopilot_tools(tenant_id: str) -> list[str]:
    try:
        from store.settings import get_agent_settings

        return list(get_agent_settings(tenant_id).get("autopilot_tools", []) or [])
    except Exception:
        return []


def check_permission(tool_name: str, *, confirm: bool = False, tenant_id: str = "default") -> None:
    """Raise PermissionDenied if a submit-class tool isn't authorized.

    read/write pass (write is reversible and audited at the call site). submit-class
    tools require an explicit per-action confirm or membership in the tenant's
    autopilot allowlist.
    """
    tool = get_tool(tool_name)
    side_effect = tool.side_effect if tool else WRITE
    if side_effect in (READ, WRITE):
        return
    if confirm or tool_name in _autopilot_tools(tenant_id):
        return
    raise PermissionDenied(
        f"Tool '{tool_name}' has external side effects and is not authorized. "
        f"Pass confirm=true for this action, or add it to autopilot in settings."
    )


# ── Built-in tools (canonical source; mcp/manifest.py delegates here) ──────────
_BUILTINS = [
    Tool("shortlistr.status", "Pipeline + application status counts (how the search is going).",
         READ, {}, None),
    Tool("shortlistr.list_jobs", "List jobs by status (default 'inbox'). Returns id/company/title.",
         READ, {"status": {"type": "string", "default": "inbox"}}, None),
    Tool("shortlistr.discover", "Run job discovery (dry-run by default). Returns counts per source.",
         WRITE, {"dry_run": {"type": "boolean", "default": True}},
         {"method": "POST", "path": "/agent/discover"}),
    Tool("shortlistr.evaluate", "Evaluate a pipeline job (A–G blocks). Requires job_id.",
         WRITE, {"job_id": {"type": "string", "required": True}},
         {"method": "POST", "path": "/agent/evaluate"}),
    Tool("shortlistr.explain", "Human-readable match bullets for a job.",
         READ, {"job_id": {"type": "string", "required": True}},
         {"method": "GET", "path": "/agent/explain/{job_id}"}),
    Tool("shortlistr.queue_apply", "Approve job for apply assist — does NOT submit application.",
         WRITE, {"job_id": {"type": "string", "required": True}},
         {"method": "POST", "path": "/agent/queue-apply"}),
    Tool("shortlistr.apply_assist", "Pre-fill ATS form via Playwright; stops before Submit.",
         SUBMIT, {"job_id": {"type": "string", "required": True}, "headless": {"type": "boolean", "default": True}},
         {"method": "POST", "path": "/agent/apply-assist"}),
    Tool("shortlistr.resolve_jobs", "Backfill missing company/title from ATS URLs.",
         WRITE, {"limit": {"type": "integer", "default": 50}},
         {"method": "POST", "path": "/agent/resolve-jobs"}),
    Tool("channel.send", "Send an email/message via a configured channel (Gmail/SMTP). External side effect.",
         SUBMIT, {"to": {"type": "string", "required": True},
                  "subject": {"type": "string", "required": True},
                  "body": {"type": "string", "required": True},
                  "channel": {"type": "string", "default": "gmail"}}),
]

for _t in _BUILTINS:
    register(_t)
