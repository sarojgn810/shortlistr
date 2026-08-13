"""Long operations announce themselves instead of hanging.

``dispatch._discover`` calls ``run_scheduled_scan()`` inline, which is 2.5-8.5
minutes of work, and the dashboard client gives up on a request after 90s. Voice
therefore enqueues the scan the way ``POST /jobs/discover`` already does, says
how long it will take, and lets the HUD poll ``/jobs/discover/status``.
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))


def test_scan_enqueues_and_returns_at_once(monkeypatch):
    from store import db
    from voice import intents

    queued = []
    monkeypatch.setattr(db, "enqueue_task", lambda t, p: queued.append((t, p)) or 7)

    out = intents.run(intents.resolve("scan for jobs"))

    assert queued == [("discover", {"dry_run": False})]
    assert out["watch"] == {"kind": "discover"}


def test_scan_never_calls_the_blocking_tool(monkeypatch):
    from agent import dispatch
    from store import db
    from voice import intents

    monkeypatch.setattr(db, "enqueue_task", lambda t, p: 7)
    called = []
    monkeypatch.setattr(dispatch, "call_tool", lambda name, *a, **k: called.append(name) or {})

    intents.run(intents.resolve("run discovery"))

    assert "shortlistr.discover" not in called


def test_the_spoken_ack_states_a_duration(monkeypatch):
    from store import db
    from voice import intents

    monkeypatch.setattr(db, "enqueue_task", lambda t, p: 7)

    out = intents.run(intents.resolve("scan for jobs"))

    assert "minute" in out["speech"], out["speech"]


def test_slow_tools_warn_before_running(monkeypatch):
    from agent import dispatch
    from voice import intents

    monkeypatch.setattr(dispatch, "call_tool", lambda name, *a, **k: {"score": 4.0})

    out = intents.run(intents.resolve("evaluate this one", job_id="a1b2c3d4"))

    assert "second" in out["ack"], out
