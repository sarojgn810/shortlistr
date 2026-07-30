"""MCP client — connect outbound to user-configured MCP servers.

The official `mcp` SDK is async; we expose small sync wrappers (asyncio.run over
short-lived sessions) so the rest of the sync codebase can use it. The SDK is
imported lazily so the app (and tests) run without it installed — calls raise
MCPUnavailable until `pip install mcp`.

Server config shape (from config.MCP_SERVERS):
    {"name": "fs", "transport": "stdio", "command": "mcp-server-filesystem",
     "args": ["/path"], "side_effect_overrides": {"read_file": "read"}}
    {"name": "x", "transport": "http", "url": "https://...", "secret_ref": "X_TOKEN"}
"""

from __future__ import annotations

import asyncio
from typing import Any


class MCPUnavailable(RuntimeError):
    pass


def _require_sdk():
    try:
        import mcp  # noqa: F401
    except Exception as e:  # SDK not installed
        raise MCPUnavailable("MCP SDK not installed — run: pip install mcp") from e


async def _session(server: dict):
    """Open an MCP ClientSession for a server config (stdio or http)."""
    from mcp import ClientSession
    from secrets_store import get_secret

    transport = (server.get("transport") or "stdio").lower()
    if transport == "stdio":
        from mcp import StdioServerParameters
        from mcp.client.stdio import stdio_client

        params = StdioServerParameters(
            command=server["command"], args=list(server.get("args") or [])
        )
        return stdio_client(params), ClientSession
    # http / streamable-http / sse
    from mcp.client.streamable_http import streamablehttp_client

    headers = {}
    ref = server.get("secret_ref")
    if ref and get_secret(ref):
        headers["Authorization"] = f"Bearer {get_secret(ref)}"
    return streamablehttp_client(server["url"], headers=headers), ClientSession


async def _list_tools_async(server: dict) -> list[dict]:
    transport_cm, ClientSession = await _session(server)
    async with transport_cm as streams:
        read, write = streams[0], streams[1]
        async with ClientSession(read, write) as session:
            await session.initialize()
            resp = await session.list_tools()
            return [
                {"name": t.name, "description": t.description or "",
                 "input_schema": getattr(t, "inputSchema", {}) or {}}
                for t in resp.tools
            ]


async def _call_tool_async(server: dict, tool: str, args: dict) -> Any:
    transport_cm, ClientSession = await _session(server)
    async with transport_cm as streams:
        read, write = streams[0], streams[1]
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool, args or {})
            return getattr(result, "content", result)


def list_tools(server: dict) -> list[dict]:
    _require_sdk()
    return asyncio.run(_list_tools_async(server))


def call_tool(server: dict, tool: str, args: dict | None = None) -> Any:
    _require_sdk()
    return asyncio.run(_call_tool_async(server, tool, args or {}))
