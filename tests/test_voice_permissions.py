"""Voice inherits the existing permission gate — it does not get its own.

The temptation when adding a fast path is to call the handler directly, since
the router already knows which tool it wants. That would route around
``check_permission`` and hand a microphone the power to submit applications.
Every test here exists to keep the fast path going through
``dispatch.call_tool``.
"""

from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))

JOB = "a1b2c3d4"


@pytest.fixture
def no_autopilot(monkeypatch):
    from agent import registry

    monkeypatch.setattr(registry, "_autopilot_tools", lambda tenant: [])


@pytest.fixture
def spy_handler(monkeypatch):
    """Record calls to a built-in handler, leaving the real gate in the path.

    ``_BUILTIN_HANDLERS`` is built at import and holds direct function
    references, so patching ``dispatch._skip`` never reaches the dict. Patch
    the entry.
    """
    from agent import dispatch

    def install(tool: str, result=None):
        calls: list = []
        monkeypatch.setitem(
            dispatch._BUILTIN_HANDLERS, tool, lambda args: calls.append(args) or (result or {})
        )
        return calls

    return install


def test_submit_tool_asks_instead_of_running(no_autopilot, spy_handler):
    from voice import intents

    ran = spy_handler("shortlistr.apply_assist")

    out = intents.run(intents.resolve("apply to this one", job_id=JOB))

    assert ran == [], "apply-assist must not run before the user confirms"
    assert out["pending_confirm"]["tool"] == "shortlistr.apply_assist"
    assert out["pending_confirm"]["args"]["job_id"] == JOB


def test_confirmed_submit_runs(no_autopilot, spy_handler):
    from voice import intents

    ran = spy_handler("shortlistr.apply_assist", {"ok": True})

    out = intents.confirm("shortlistr.apply_assist", {"job_id": JOB})

    assert ran == [{"job_id": JOB}]
    assert not out.get("pending_confirm")


def test_autopilot_allowlist_still_governs(monkeypatch, spy_handler):
    from agent import registry
    from voice import intents

    # The user opted this tool into autopilot in settings. Voice must honour
    # that rather than inventing a stricter rule of its own.
    monkeypatch.setattr(registry, "_autopilot_tools", lambda tenant: ["shortlistr.apply_assist"])
    ran = spy_handler("shortlistr.apply_assist", {"ok": True})

    out = intents.run(intents.resolve("apply to this one", job_id=JOB))

    assert ran == [{"job_id": JOB}]
    assert not out.get("pending_confirm")


def test_write_tools_run_without_a_prompt(no_autopilot, spy_handler):
    from voice import intents

    ran = spy_handler("shortlistr.skip", {"ok": True})

    out = intents.run(intents.resolve("skip", offer={"job_id": JOB, "options": ["skip"]}))

    assert ran == [{"job_id": JOB}]
    assert not out.get("pending_confirm")


def test_dispatch_is_the_only_route_to_a_handler(monkeypatch):
    from agent import dispatch
    from voice import intents

    # If anything ever calls _BUILTIN_HANDLERS directly, this stops seeing the
    # call and the test fails — which is the point.
    seen = []
    real = dispatch.call_tool
    monkeypatch.setattr(
        dispatch, "call_tool", lambda name, args=None, **kw: seen.append(name) or {}
    )
    intents.run(intents.resolve("what's my status"))
    assert seen == ["shortlistr.status"]
    assert real is not dispatch.call_tool
