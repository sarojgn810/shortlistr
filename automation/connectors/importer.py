"""Import tools from configured MCP servers into the agent registry.

Each external tool becomes `mcp.<server>.<tool>` and is registered with a
conservatively-inferred side-effect class, so it inherits the F2 permission gate.
"""

from __future__ import annotations

import logging
import re

from agent.registry import READ, SUBMIT, Tool, register

logger = logging.getLogger(__name__)

# Names that clearly only read state; everything else defaults to submit (gated).
_READ_RE = re.compile(r"^(get|list|search|read|fetch|find|query|explain|view|show|describe)[_\-]?", re.I)


def infer_side_effect(tool_name: str, overrides: dict | None = None) -> str:
    if overrides and tool_name in overrides:
        val = str(overrides[tool_name]).lower()
        if val in (READ, "write", SUBMIT):
            return val
    return READ if _READ_RE.match(tool_name or "") else SUBMIT


def import_mcp_tools(servers=None, client=None) -> list[str]:
    """Connect to each configured MCP server and register its tools. Returns names."""
    if servers is None:
        from config import MCP_SERVERS

        servers = MCP_SERVERS
    if client is None:
        from connectors import client as client  # noqa: PLW0127

    registered: list[str] = []
    for server in servers or []:
        name = server.get("name") or "mcp"
        overrides = server.get("side_effect_overrides") or {}
        try:
            tools = client.list_tools(server)
        except Exception as e:
            logger.warning("MCP server '%s': could not list tools (%s)", name, e)
            continue
        for t in tools:
            qualified = f"mcp.{name}.{t['name']}"
            register(
                Tool(
                    qualified,
                    t.get("description", ""),
                    infer_side_effect(t["name"], overrides),
                    t.get("input_schema") or {},
                    None,
                )
            )
            registered.append(qualified)
        logger.info("MCP server '%s': imported %d tools", name, len(tools))
    return registered
