"""Choosing a model in Connections has to be what makes it get used.

Enabling Local AI pulled the model and wrote a status file saying "ready", and
then never touched `llm.provider`. A profile that has not picked one reads back
as "none" (see get_profile_for_ui), and get_llm() returns None for "none" — so
on a machine with a working local model every evaluation still fell through to
keyword scoring and the UI showed "Basic score" on all of them.

The other half matters just as much: someone who deliberately chose a cloud
provider must not be moved off it because they also installed a local model.
"""

from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))


@pytest.fixture
def profile(monkeypatch, tmp_path):
    """A profile store pointed at a temp file, never the developer's own."""
    import profile_store as ps

    monkeypatch.setattr(ps, "PROFILE_PATH", str(tmp_path / "profile.yml"))

    def _save(**over):
        body = {"name": "A B", "email": "a@b.com", "target_titles": ["SRE"]}
        body.update(over)
        return ps.save_profile_from_ui(body)

    return ps, _save


def test_enabling_local_ai_switches_a_profile_that_never_chose(profile):
    """The reported bug: a ready local model, and every score still "Basic"."""
    ps, save = profile
    save(llm_provider="none")

    ps.adopt_local_ai_provider("qwen3:0.6b")

    out = ps.get_profile_for_ui()
    assert out["llm_provider"] == "auto"
    assert out["llm_model"] == "qwen3:0.6b"


def test_the_chosen_model_is_recorded(profile):
    ps, save = profile
    save(llm_provider="none")
    ps.adopt_local_ai_provider("gemma3:12b")
    assert ps.get_profile_for_ui()["llm_model"] == "gemma3:12b"


@pytest.mark.parametrize("cloud", ["groq", "openai", "anthropic", "gemini", "grok"])
def test_a_deliberate_cloud_choice_is_never_overridden(profile, cloud):
    """Installing a local model must not move someone off what they picked."""
    ps, save = profile
    save(llm_provider=cloud, llm_model="some-cloud-model")

    ps.adopt_local_ai_provider("qwen3:0.6b")

    out = ps.get_profile_for_ui()
    assert out["llm_provider"] == cloud
    assert out["llm_model"] == "some-cloud-model"


def test_auto_stays_auto_and_just_records_the_model(profile):
    """auto already prefers a ready local model; only the tag needs updating."""
    ps, save = profile
    save(llm_provider="auto")

    ps.adopt_local_ai_provider("qwen3:0.6b")

    out = ps.get_profile_for_ui()
    assert out["llm_provider"] == "auto"
    assert out["llm_model"] == "qwen3:0.6b"


def test_no_model_named_still_switches_the_provider(profile):
    """Adopting an already-pulled model passes no tag; the switch still matters."""
    ps, save = profile
    save(llm_provider="none")

    ps.adopt_local_ai_provider("")

    assert ps.get_profile_for_ui()["llm_provider"] == "auto"


def test_an_incomplete_profile_does_not_break_local_ai_setup(profile):
    """Before onboarding there is nothing to merge onto. That is onboarding's
    problem to solve, not a reason to fail the setup the user just asked for."""
    ps, _ = profile
    assert ps.adopt_local_ai_provider("qwen3:0.6b") is not None


def test_the_connections_call_adopts_the_provider(monkeypatch):
    """The wiring, not just the helper."""
    import connections_store as cs

    monkeypatch.setattr("llm.local_ai.ensure_local_ai_async", lambda **k: {"ready": True})
    monkeypatch.setattr("llm.local_ai.local_ai_status",
                        lambda *a, **k: {"ready": True, "model": "qwen3:0.6b"})
    seen: list[str] = []
    monkeypatch.setattr("profile_store.adopt_local_ai_provider",
                        lambda model="": seen.append(model))

    cs.ensure_local_ai_from_ui(model="qwen3:0.6b")
    assert seen == ["qwen3:0.6b"], "selecting a model did not point the profile at it"


def test_a_failure_to_adopt_does_not_fail_the_setup(monkeypatch):
    import connections_store as cs

    monkeypatch.setattr("llm.local_ai.ensure_local_ai_async", lambda **k: {"ready": True})
    monkeypatch.setattr("llm.local_ai.local_ai_status", lambda *a, **k: {"ready": True})

    def boom(model=""):
        raise RuntimeError("profile is unwritable")

    monkeypatch.setattr("profile_store.adopt_local_ai_provider", boom)
    assert cs.ensure_local_ai_from_ui()["ok"] is True
