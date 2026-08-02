"""
Agent / MCP tool manifest (J3.2).

Documents stable tool contracts for IDE agents and future MCP server.
HTTP equivalents live under /agent/* in automation/api/main.py.
"""

from __future__ import annotations

from agent.registry import list_tools as _registry_tools

# Canonical tool definitions now live in agent/registry.py (with side-effect
# classes + the permission gate). This module stays as the stable MCP/IDE entry.


def list_tools() -> list[dict]:
    return _registry_tools()


# Back-compat alias for callers importing the list directly.
AGENT_TOOLS: list[dict] = _registry_tools()
