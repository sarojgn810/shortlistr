"""Local speech-to-text.

The behaviour worth pinning is the degrade path. ``faster-whisper`` is an
optional dependency, so a clone that skipped it must still boot the API and get
a readable reason pointing at Connections — not a traceback, and not a hint to
run something in a terminal.
"""

from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))

# numpy arrives with faster-whisper. An install that predates this feature has
# neither, and must skip rather than error the whole file.
np = pytest.importorskip("numpy")


def test_status_never_raises_and_reports_the_library():
    from voice import stt

    status = stt.voice_status()
    assert "library_installed" in status
    assert "available" in status


def test_missing_library_degrades_with_a_ui_pointer(monkeypatch):
    from voice import stt

    monkeypatch.setattr(stt, "library_available", lambda: False)

    out = stt.transcribe(np.zeros(1600, dtype=np.float32))

    assert out["available"] is False
    assert out["text"] == ""
    # CLAUDE.md: once make start has run, setup lives in the dashboard. A
    # reason that says "pip install" would be a regression in the product, not
    # just the copy.
    assert "Connections" in out["reason"]
    for terminal_hint in ("pip install", "make install", "playwright install"):
        assert terminal_hint not in out["reason"]


def test_ensure_is_a_noop_without_the_library(monkeypatch):
    from voice import stt

    monkeypatch.setattr(stt, "library_available", lambda: False)
    # Must not spawn a thread that will only fail.
    assert stt.ensure_voice_async()["available"] is False


def test_load_failure_is_reported_not_raised(monkeypatch):
    from voice import stt

    monkeypatch.setattr(stt, "library_available", lambda: True)
    monkeypatch.setattr(stt, "load_model", lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))

    out = stt.transcribe(np.zeros(1600, dtype=np.float32))

    assert out["available"] is False
    assert "disk full" in out["reason"]


def test_silence_transcribes_to_nothing_rather_than_hallucinating():
    from voice import stt

    if not (stt.library_available() and stt.model_cached()):
        pytest.skip("speech model not downloaded on this machine")

    # Whisper is known to emit filler on pure silence ("Thank you.", "you").
    # A command router acting on that would be worse than hearing nothing, so
    # this documents what the endpoint actually returns for a silent segment.
    out = stt.transcribe(np.zeros(16000, dtype=np.float32))

    assert out["available"] is True
    assert len(out["text"]) < 40, out["text"]


def test_model_is_loaded_once_and_kept_warm(monkeypatch):
    from voice import stt

    if not (stt.library_available() and stt.model_cached()):
        pytest.skip("speech model not downloaded on this machine")

    loads = []
    real = stt.load_model

    def counting(name=None):
        loads.append(name)
        return real(name)

    monkeypatch.setattr(stt, "load_model", counting)
    stt.transcribe(np.zeros(1600, dtype=np.float32))
    stt.transcribe(np.zeros(1600, dtype=np.float32))

    # Two calls into load_model, but the singleton means only one real load —
    # which is the whole reason a 200ms transcription is possible at all.
    assert len(loads) == 2
    assert stt._model is not None


def test_truncated_model_does_not_count_as_downloaded(tmp_path, monkeypatch):
    """A killed download leaves model.bin pointing at a partial blob.

    Found the hard way: an interrupted fetch left a 65MB stub of a 145MB model.
    The file existed, so the probe said cached, so the setup card said "Ready",
    and every utterance then failed inside ctranslate2 with "File model.bin is
    incomplete". Reporting ready while nothing works points the user away from
    the real problem.
    """
    from voice import stt

    repo = tmp_path / "models--Systran--faster-whisper-tiny.en"
    snap = repo / "snapshots" / "abc123"
    snap.mkdir(parents=True)
    (repo / "blobs").mkdir()
    monkeypatch.setattr(stt, "_hf_cache_dir", lambda: str(tmp_path))

    (snap / "model.bin").write_bytes(b"\0" * 1_000_000)      # truncated
    assert stt.model_cached("tiny.en") is False

    (snap / "model.bin").write_bytes(b"\0" * 80_000_000)     # plausible
    assert stt.model_cached("tiny.en") is True


def test_the_floor_is_per_model_not_flat(tmp_path, monkeypatch):
    """The real stub was 67MB — bigger than a *complete* tiny.en.

    A single global size floor therefore cannot work: set it low enough to
    accept tiny.en and it accepts a half-downloaded base.en too.
    """
    from voice import stt

    monkeypatch.setattr(stt, "_hf_cache_dir", lambda: str(tmp_path))

    for name in ("tiny.en", "base.en"):
        snap = tmp_path / f"models--Systran--faster-whisper-{name}" / "snapshots" / "s"
        snap.mkdir(parents=True)
        (tmp_path / f"models--Systran--faster-whisper-{name}" / "blobs").mkdir()
        (snap / "model.bin").write_bytes(b"\0" * 67_000_000)

    assert stt.model_cached("tiny.en") is True    # complete
    assert stt.model_cached("base.en") is False   # less than half of ~145MB


def test_partial_download_marker_beats_a_present_file(tmp_path, monkeypatch):
    from voice import stt

    repo = tmp_path / "models--Systran--faster-whisper-tiny.en"
    snap = repo / "snapshots" / "abc123"
    snap.mkdir(parents=True)
    blobs = repo / "blobs"
    blobs.mkdir()
    monkeypatch.setattr(stt, "_hf_cache_dir", lambda: str(tmp_path))

    (snap / "model.bin").write_bytes(b"\0" * 80_000_000)
    assert stt.model_cached("tiny.en") is True

    # A fetch still in flight, or one that died mid-write.
    (blobs / "deadbeef.incomplete").write_bytes(b"\0" * 10)
    assert stt.model_cached("tiny.en") is False


def test_status_stops_claiming_ready_after_a_load_failure(monkeypatch):
    from voice import stt

    monkeypatch.setattr(stt, "library_available", lambda: True)
    monkeypatch.setattr(stt, "model_cached", lambda name=None: True)
    monkeypatch.setattr(stt, "_model", None)
    monkeypatch.setattr(
        stt, "_read_status",
        lambda: {"phase": "error", "error": "File model.bin is incomplete", "model": "tiny.en"},
    )

    status = stt.voice_status()

    assert status["model_downloaded"] is True   # the file really is there
    assert status["available"] is False         # but it does not load
    assert "incomplete" in status["reason"]
