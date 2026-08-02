"""Tool registry + permission gate tests."""

from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))


def test_list_tools_have_side_effect_class():
    from agent.registry import list_tools

    tools = {t["name"]: t for t in list_tools()}
    assert tools["shortlistr.explain"]["side_effect"] == "read"
    assert tools["shortlistr.evaluate"]["side_effect"] == "write"
    assert tools["shortlistr.apply_assist"]["side_effect"] == "submit"


def test_read_and_write_always_allowed():
    from agent.registry import check_permission

    check_permission("shortlistr.explain")   # read
    check_permission("shortlistr.evaluate")   # write
    # no exception → allowed


def test_submit_requires_confirm(monkeypatch):
    from agent import registry

    monkeypatch.setattr(registry, "_autopilot_tools", lambda tenant: [])
    with pytest.raises(registry.PermissionDenied):
        registry.check_permission("shortlistr.apply_assist")
    # explicit confirm authorizes it
    registry.check_permission("shortlistr.apply_assist", confirm=True)


def test_submit_allowed_via_autopilot(monkeypatch):
    from agent import registry

    monkeypatch.setattr(registry, "_autopilot_tools", lambda tenant: ["shortlistr.apply_assist"])
    registry.check_permission("shortlistr.apply_assist")  # no confirm needed when on autopilot
