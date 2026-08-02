"""Local AI uses a model the machine already has, if it can run it.

Two failures met on a real laptop, in this order:

1. Ollama was installed, running and holding gemma3:12b, but the app reported
   "not ready" because its own recommended tag (llama3.2:3b) had failed to
   download. A capable model was sitting on disk and went unused.
2. Adopting the *largest* pulled model then picked that 8.1GB gemma3:12b on an
   18GB laptop, and Ollama answered "model failed to load, this may be due to
   resource limitations".

So the rule is the largest installed model that this machine can actually load,
at the same ratio hardware.py already uses (it sizes a ~2GB 3B model at a 12GB
machine, because the user still has a browser open).
"""

from __future__ import annotations

import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))

GB = 1_000_000_000


@pytest.fixture
def ram(monkeypatch):
    """Pin the machine size so the budget is not the test runner's RAM."""
    def _set(gb: float):
        monkeypatch.setattr("llm.hardware.detect_system", lambda *a, **k: {"ram_gb": gb})
    return _set


def _installed(monkeypatch, rows):
    from llm import local_ai

    monkeypatch.setattr(local_ai, "installed_models", lambda *a, **k: rows)


# ── picking ──────────────────────────────────────────────────────────────────

def test_the_biggest_model_that_fits_wins(monkeypatch, ram):
    from llm.local_ai import usable_local_model

    ram(18)
    _installed(monkeypatch, [("gemma3:12b", 8 * GB), ("qwen2.5:1.5b", 1 * GB)])
    assert usable_local_model() == "qwen2.5:1.5b"


def test_a_big_model_is_used_on_a_big_machine(monkeypatch, ram):
    """The cap is about this laptop, not a dislike of large models."""
    from llm.local_ai import usable_local_model

    ram(64)
    _installed(monkeypatch, [("gemma3:12b", 8 * GB), ("qwen2.5:1.5b", 1 * GB)])
    assert usable_local_model() == "gemma3:12b"


def test_nothing_pulled_means_no_model(monkeypatch, ram):
    from llm.local_ai import usable_local_model

    ram(18)
    _installed(monkeypatch, [])
    assert usable_local_model() == ""


def test_no_model_small_enough_means_no_model(monkeypatch, ram):
    """Better to say "not ready" than to pick one that 500s on first use."""
    from llm.local_ai import usable_local_model

    ram(8)
    _installed(monkeypatch, [("gemma3:12b", 8 * GB)])
    assert usable_local_model() == ""


def test_non_chat_models_are_never_picked(monkeypatch, ram):
    """An embedding model would look "ready" and then fail every evaluation."""
    from llm.local_ai import usable_local_model

    ram(18)
    _installed(monkeypatch, [
        ("nomic-embed-text", 1 * GB),
        ("mxbai-embed-large", 1 * GB),
        ("qwen2.5:1.5b", 1 * GB),
    ])
    assert usable_local_model() == "qwen2.5:1.5b"


def test_unknown_ram_does_not_block_a_pick(monkeypatch):
    """If the machine cannot be sized, trying is better than refusing."""
    from llm.local_ai import usable_local_model

    monkeypatch.setattr("llm.hardware.detect_system", lambda *a, **k: {})
    _installed(monkeypatch, [("qwen2.5:1.5b", 1 * GB)])
    assert usable_local_model() == "qwen2.5:1.5b"


# ── reporting it ─────────────────────────────────────────────────────────────

def _stale_pull_error(monkeypatch, local_ai, tmp_path):
    """The state a failed `ollama pull` leaves behind on disk."""
    state = tmp_path / "local_ai.json"
    state.write_text(json.dumps({
        "phase": "error",
        "message": "pull model manifest: connection refused",
        "error": "pull model manifest: connection refused",
        "model": "llama3.2:3b",
    }))
    monkeypatch.setattr(local_ai, "_status_path", lambda *a, **k: str(state))

def test_status_adopts_an_installed_model_instead_of_saying_not_ready(monkeypatch, tmp_path):
    """The real bug: a failed llama3.2:3b pull hid a perfectly good local model."""
    from llm import local_ai

    _stale_pull_error(monkeypatch, local_ai, tmp_path)
    monkeypatch.setattr(local_ai, "_ollama_reachable", lambda *a, **k: True)
    monkeypatch.setattr(local_ai, "_model_present", lambda *a, **k: False)
    monkeypatch.setattr(local_ai, "usable_local_model", lambda *a, **k: "qwen2.5:1.5b")

    st = local_ai.local_ai_status()
    assert st["ready"] is True
    assert st["model"] == "qwen2.5:1.5b"
    assert st["adopted_installed_model"] == "qwen2.5:1.5b"
    assert st["error"] is None, "a stale pull error must not survive a working model"


def test_nothing_usable_leaves_the_error_intact(monkeypatch, tmp_path):
    """With no model at all the user still needs to see why the pull failed."""
    from llm import local_ai

    _stale_pull_error(monkeypatch, local_ai, tmp_path)
    monkeypatch.setattr(local_ai, "_ollama_reachable", lambda *a, **k: True)
    monkeypatch.setattr(local_ai, "_model_present", lambda *a, **k: False)
    monkeypatch.setattr(local_ai, "usable_local_model", lambda *a, **k: "")

    st = local_ai.local_ai_status()
    assert st["ready"] is False
    assert st["phase"] == "error"


def test_a_stopped_ollama_is_not_ready(monkeypatch, tmp_path):
    from llm import local_ai

    _stale_pull_error(monkeypatch, local_ai, tmp_path)
    monkeypatch.setattr(local_ai, "_ollama_reachable", lambda *a, **k: False)
    picked = []
    monkeypatch.setattr(local_ai, "usable_local_model",
                        lambda *a, **k: picked.append(1) or "qwen2.5:1.5b")

    st = local_ai.local_ai_status()
    assert st["ready"] is False
    assert not picked, "asked Ollama for its models while it was not running"


# ── listing ──────────────────────────────────────────────────────────────────

def test_installed_models_are_returned_largest_first(monkeypatch):
    from llm import local_ai

    class Resp:
        status_code = 200

        def raise_for_status(self): pass

        def json(self):
            return {"models": [{"name": "small", "size": 1 * GB},
                               {"name": "big", "size": 9 * GB}]}

    monkeypatch.setattr(local_ai.requests, "get", lambda *a, **k: Resp())
    assert [n for n, _ in local_ai.installed_models()] == ["big", "small"]


def test_an_unreachable_ollama_lists_nothing(monkeypatch):
    from llm import local_ai

    def boom(*a, **k):
        raise OSError("connection refused")

    monkeypatch.setattr(local_ai.requests, "get", boom)
    assert local_ai.installed_models() == []


# ── choosing a provider ──────────────────────────────────────────────────────
#
# The status display was only half of it. _resolve_auto tried the configured tag
# and the recommended one and nothing else, so a machine holding gemma3:12b with
# neither of those pulled went to the cloud — or, with no key, to heuristics.

def test_auto_uses_an_installed_model_rather_than_the_cloud(monkeypatch):
    import llm

    monkeypatch.setattr("llm.local_ai.is_local_ready", lambda *a, **k: False)
    monkeypatch.setattr("llm.local_ai.usable_local_model", lambda *a, **k: "qwen2.5:1.5b")

    provider, name = llm._resolve_auto(api_key="", model="", ollama_url="http://x")
    assert name == "ollama"
    assert provider.model == "qwen2.5:1.5b"


def test_a_ready_configured_model_still_wins(monkeypatch):
    """Adoption is a fallback, not an override of what the user chose."""
    import llm

    monkeypatch.setattr("llm.local_ai.is_local_ready", lambda url, m=None: m == "llama3.2:3b")
    monkeypatch.setattr("llm.local_ai.usable_local_model", lambda *a, **k: "qwen2.5:1.5b")

    provider, name = llm._resolve_auto(api_key="", model="llama3.2:3b", ollama_url="http://x")
    assert provider.model == "llama3.2:3b"


def test_no_local_model_falls_through_to_the_cloud_key(monkeypatch):
    import llm

    monkeypatch.setattr("llm.local_ai.is_local_ready", lambda *a, **k: False)
    monkeypatch.setattr("llm.local_ai.usable_local_model", lambda *a, **k: "")

    _, name = llm._resolve_auto(api_key="gsk_" + "x" * 20, model="",
                                ollama_url="http://x")
    assert name != "ollama", "claimed a local model that is not installed"


# ── the card must not flicker ────────────────────────────────────────────────
#
# Setting up Local AI worked, and seconds later the card reverted to "set up
# Local AI" and had to be clicked again. _model_present returned False both when
# Ollama answered "no such model" and when it did not answer at all — and while
# it is busy pulling or loading it stops answering /api/tags within the timeout.
# A ready state was therefore erased by its own success.

def _status_file(monkeypatch, local_ai, tmp_path, **over):
    import json

    state = tmp_path / "local_ai.json"
    payload = {"phase": "ready", "message": "Local AI ready",
               "model": "qwen2.5:0.5b", "model_ready": True, "error": None}
    payload.update(over)
    state.write_text(json.dumps(payload))
    monkeypatch.setattr(local_ai, "_status_path", lambda *a, **k: str(state))
    monkeypatch.setattr(local_ai, "_ollama_reachable", lambda *a, **k: True)
    monkeypatch.setattr(local_ai, "usable_local_model", lambda *a, **k: "")


def test_an_unanswered_probe_keeps_the_last_known_state(monkeypatch, tmp_path):
    """Busy is not absent. This is the flicker."""
    from llm import local_ai

    _status_file(monkeypatch, local_ai, tmp_path)
    monkeypatch.setattr(local_ai, "_model_present", lambda *a, **k: None)

    st = local_ai.local_ai_status()
    assert st["ready"] is True
    assert st["phase"] == "ready"
    assert st["probe_unavailable"] is True


def test_a_definite_no_downgrades_the_phase(monkeypatch, tmp_path):
    """Phase only ever moved up, so a removed model left the card claiming ready."""
    from llm import local_ai

    _status_file(monkeypatch, local_ai, tmp_path)
    monkeypatch.setattr(local_ai, "_model_present", lambda *a, **k: False)

    st = local_ai.local_ai_status()
    assert st["ready"] is False
    assert st["phase"] != "ready"


def test_a_present_model_stays_ready(monkeypatch, tmp_path):
    from llm import local_ai

    _status_file(monkeypatch, local_ai, tmp_path)
    monkeypatch.setattr(local_ai, "_model_present", lambda *a, **k: True)
    assert local_ai.local_ai_status()["ready"] is True


def test_an_unreachable_ollama_reports_unknown_not_absent():
    """Nothing listening is a probe that could not be answered."""
    from llm.local_ai import _model_present

    assert _model_present("http://127.0.0.1:9", "any") is None
