"""Stop paying for a search backend that just refused us.

DuckDuckGo answers a bot challenge in about 12 seconds. Building one prep bundle
makes six searches, so when it is challenging — which it is, persistently — that
was 72 of the 76 seconds spent generating a prep document, all of it waiting for
six guaranteed failures.

Nothing about the answer changes between those six calls. After the first
refusal the rest are skipped, and the document already explains that the reading
list needs a search key.

Prep on a job: 76s -> 15s on the first run, 1.9s once the state is known.
"""

from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))


@pytest.fixture(autouse=True)
def clear_backoff():
    """The flag is process-level; leaking it would order-couple these tests."""
    from prep import research

    research._DDG_BLOCKED_UNTIL = 0.0
    yield
    research._DDG_BLOCKED_UNTIL = 0.0


def _no_other_backends(monkeypatch):
    """Isolate DuckDuckGo: no CSE, no SerpAPI, no Serper."""
    from prep import research

    monkeypatch.setattr(research, "_serper_organic", lambda *a, **k: [])
    monkeypatch.setitem(sys.modules, "processors.search_discovery", None)


def test_a_challenge_stops_the_next_search(monkeypatch):
    from prep import research

    _no_other_backends(monkeypatch)
    calls = []

    def challenged(query, num=6):
        calls.append(query)
        raise RuntimeError("DuckDuckGo challenged (HTTP 202)")

    monkeypatch.setattr(research, "_duckduckgo_organic", challenged)

    research.web_organic("how does Acme interview")
    research.web_organic("Acme SRE hiring process")
    research.web_organic("Acme on-call culture")

    assert len(calls) == 1, f"kept asking a backend that refused: {len(calls)} calls"


def test_a_working_backend_is_not_backed_off(monkeypatch):
    from prep import research

    _no_other_backends(monkeypatch)
    hit = [{"title": "t", "link": "https://sre.google/", "snippet": "s"}]
    calls = []
    monkeypatch.setattr(research, "_duckduckgo_organic",
                        lambda q, num=6: calls.append(q) or hit)

    for _ in range(3):
        assert research.web_organic("x") == hit
    assert len(calls) == 3, "backed off a backend that was answering fine"


def test_the_backoff_expires(monkeypatch):
    """Blocked is a cooldown, not a life sentence — DDG recovers."""
    from prep import research

    _no_other_backends(monkeypatch)
    research._mark_ddg_blocked()
    assert research._ddg_blocked() is True

    # Wind the clock past the cooldown rather than sleeping through it.
    monkeypatch.setattr(research.time, "monotonic",
                        lambda: research._DDG_BLOCKED_UNTIL + 1)
    assert research._ddg_blocked() is False


def test_a_blocked_search_still_returns_a_list(monkeypatch):
    """Callers index the result; None here would take prep down."""
    from prep import research

    _no_other_backends(monkeypatch)
    research._mark_ddg_blocked()
    assert research.web_organic("anything") == []


def test_the_paid_backends_are_still_tried_while_ddg_is_blocked(monkeypatch):
    """Backing off the free tier must not disable a key the user paid for."""
    from prep import research

    research._mark_ddg_blocked()
    monkeypatch.setitem(sys.modules, "processors.search_discovery", None)
    hit = [{"title": "t", "link": "https://kubernetes.io/", "snippet": "s"}]
    monkeypatch.setattr(research, "_serper_organic", lambda *a, **k: hit)

    assert research.web_organic("x") == hit


def test_ddg_is_not_called_at_all_once_blocked(monkeypatch):
    from prep import research

    _no_other_backends(monkeypatch)
    research._mark_ddg_blocked()
    called = []
    monkeypatch.setattr(research, "_duckduckgo_organic",
                        lambda q, num=6: called.append(q) or [])

    research.web_organic("x")
    assert not called, "paid the 12s timeout despite knowing it would refuse"
