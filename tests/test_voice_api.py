"""Voice endpoints.

The response shape matters as much as the behaviour: the voice console and the
assistant dock share one client path, so /voice/command has to be a superset of
what /agent/chat already returns.
"""

from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))

fastapi_testclient = pytest.importorskip("fastapi.testclient")


@pytest.fixture
def client():
    from api.main import create_app

    return fastapi_testclient.TestClient(create_app())


def test_api_boots_without_the_speech_library(monkeypatch):
    """A clone that never installed faster-whisper must still start."""
    import builtins

    real_import = builtins.__import__

    def no_whisper(name, *args, **kwargs):
        if name.startswith("faster_whisper"):
            raise ImportError("no module named faster_whisper")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_whisper)

    from voice import stt

    status = stt.voice_status()
    assert status["library_installed"] is False
    assert status["available"] is False
    assert "Connections" in status["reason"]


def test_status_endpoint(client):
    res = client.get("/voice/status")
    assert res.status_code == 200
    assert "available" in res.json()


def test_command_ignores_speech_without_the_wake_phrase(client):
    res = client.post("/voice/command", json={"text": "I shortlisted three roles today"})

    assert res.status_code == 200
    body = res.json()
    assert body["woke"] is False
    assert body["speech"] == ""
    assert not body.get("actions")


def test_command_runs_a_fast_path_intent(client, monkeypatch):
    from agent import dispatch

    monkeypatch.setitem(
        dispatch._BUILTIN_HANDLERS,
        "shortlistr.status",
        lambda args: {"pipeline": {"pending": 4}},
    )

    res = client.post("/voice/command", json={"text": "hey shortlistr what's my status"})

    body = res.json()
    assert body["woke"] is True
    assert body["heard"] == "what's my status"
    assert "4" in body["speech"]
    # Fast path: answered without an LLM round trip.
    assert body["actions"][0]["tool"] == "shortlistr.status"


def test_command_response_is_a_superset_of_chat(client, monkeypatch):
    from agent import dispatch

    monkeypatch.setitem(dispatch._BUILTIN_HANDLERS, "shortlistr.status", lambda args: {})

    body = client.post("/voice/command", json={"text": "hey shortlistr status"}).json()

    for key in ("reply", "actions"):          # what ChatResponse already promises
        assert key in body
    for key in ("speech", "woke"):            # what voice adds
        assert key in body


def test_bare_wake_phrase_acknowledges(client):
    body = client.post("/voice/command", json={"text": "hey shortlistr"}).json()

    assert body["woke"] is True
    assert body["speech"]
    assert not body.get("actions")


def test_follow_up_window_accepts_a_bare_command(client, monkeypatch):
    from agent import dispatch

    monkeypatch.setitem(dispatch._BUILTIN_HANDLERS, "shortlistr.status", lambda args: {})

    body = client.post("/voice/command", json={"text": "status", "woken": True}).json()

    assert body["woke"] is True
    assert body["actions"][0]["tool"] == "shortlistr.status"


def test_transcribe_with_no_audio_is_not_an_error(client):
    res = client.post("/voice/transcribe", content=b"")

    assert res.status_code == 200
    assert res.json()["text"] == ""


def test_transcribe_reads_raw_pcm(client, monkeypatch):
    from voice import stt

    seen = {}
    monkeypatch.setattr(
        stt, "transcribe", lambda pcm, **kw: seen.update(n=len(pcm), peak=float(max(pcm)))
        or {"available": True, "text": "hello"}
    )

    # Two int16 samples: full scale and silence.
    res = client.post("/voice/transcribe", content=b"\xff\x7f\x00\x00")

    assert res.json()["text"] == "hello"
    assert seen["n"] == 2
    # Scaled into float range rather than handed over as raw integers.
    assert 0.9 < seen["peak"] <= 1.0
