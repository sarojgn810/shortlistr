"""MCP tool import + unified dispatch tests (client mocked; no SDK needed)."""

from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))


def test_infer_side_effect():
    from connectors.importer import infer_side_effect

    assert infer_side_effect("list_files") == "read"
    assert infer_side_effect("get_message") == "read"
    assert infer_side_effect("send_email") == "submit"      # unknown → safe default
    assert infer_side_effect("create_event") == "submit"
    assert infer_side_effect("send_email", {"send_email": "write"}) == "write"  # override


class _FakeClient:
    @staticmethod
    def list_tools(server):
        return [
            {"name": "search_docs", "description": "search", "input_schema": {}},
            {"name": "post_message", "description": "post", "input_schema": {}},
        ]

    @staticmethod
    def call_tool(server, tool, args):
        return {"echoed": tool, "args": args}


def test_import_mcp_tools_registers_namespaced_gated_tools():
    from agent import registry
    from connectors.importer import import_mcp_tools

    names = import_mcp_tools(servers=[{"name": "demo"}], client=_FakeClient())
    assert "mcp.demo.search_docs" in names
    assert registry.get_tool("mcp.demo.search_docs").side_effect == "read"
    assert registry.get_tool("mcp.demo.post_message").side_effect == "submit"


def test_dispatch_gates_and_routes(monkeypatch):
    from agent import dispatch, registry
    from connectors import client as conn_client
    from connectors.importer import import_mcp_tools

    monkeypatch.setattr(registry, "_autopilot_tools", lambda tenant: [])

    # channel.send is submit → gated without confirm
    with pytest.raises(registry.PermissionDenied):
        dispatch.call_tool("channel.send", {"to": "x@y.com", "subject": "h", "body": "b"})
    out = dispatch.call_tool(
        "channel.send",
        {"to": "x@y.com", "subject": "h", "body": "b", "dry_run": True},
        confirm=True,
    )
    assert out["ok"] is True

    # MCP read tool routes to the (mocked) client without confirm
    import_mcp_tools(servers=[{"name": "demo"}], client=_FakeClient())
    monkeypatch.setattr("config.MCP_SERVERS", [{"name": "demo", "transport": "stdio"}], raising=False)
    monkeypatch.setattr(conn_client, "call_tool", lambda server, tool, args: {"echoed": tool})
    res = dispatch.call_tool("mcp.demo.search_docs", {"q": "sre"})
    assert res == {"echoed": "search_docs"}
