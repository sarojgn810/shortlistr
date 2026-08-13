"""Local speech-to-text — faster-whisper, on this machine, no network.

Shaped after ``llm/local_ai.py``: a background thread does the download, a
status JSON is what the dashboard polls, and every entry point degrades to a
readable reason rather than an exception.

Two things are load-bearing:

*The model is a module-level singleton.* Loading costs 1-3s; doing it per
request would dwarf the 200-400ms transcription it exists to serve. Note that
``make api`` runs with ``--reload``, so saving a file drops the warm model and
the next utterance is slow — that is the reload, not a regression.

*The import is optional.* ``faster-whisper`` pulls ctranslate2, and a clone that
has not installed it must still boot the API. Nothing here imports the library
at module scope.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from typing import Any

from voice import vocabulary

logger = logging.getLogger(__name__)

# tiny.en, measured at 169-218ms per command utterance on an M-series CPU
# against base.en's ~400ms. Commands survive the accuracy drop because the
# router matches on shape, not spelling, and the wake matcher already tolerates
# what Whisper does to a coined name. Set voice.model in profile.yml to base.en
# if long open questions matter more than latency.
DEFAULT_MODEL = "tiny.en"
# int8 is the point of faster-whisper on a laptop: ~4x less memory than fp32 and
# faster on CPU, with no accuracy loss that survives a microphone.
COMPUTE_TYPE = "int8"
SAMPLE_RATE = 16000

_lock = threading.Lock()
_model: Any = None
_model_name: str | None = None
_ensure_thread: threading.Thread | None = None


def _data_dir() -> str:
    try:
        from config import DATA_DIR

        return DATA_DIR
    except Exception:
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        return os.path.join(root, "data")


def _status_path() -> str:
    return os.path.join(_data_dir(), "voice_status.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def configured_model() -> str:
    try:
        from config import VOICE_CONFIG

        return str(VOICE_CONFIG.get("model") or DEFAULT_MODEL)
    except Exception:
        return DEFAULT_MODEL


def library_available() -> bool:
    try:
        import faster_whisper  # noqa: F401

        return True
    except Exception:
        return False


def _hf_cache_dir() -> str:
    for var in ("HUGGINGFACE_HUB_CACHE", "HF_HUB_CACHE"):
        if os.environ.get(var):
            return os.environ[var]
    home = os.environ.get("HF_HOME") or os.path.join(os.path.expanduser("~"), ".cache", "huggingface")
    return os.path.join(home, "hub")


# Roughly 80% of each model.bin's real size, so a complete download always
# clears the bar and a partial one does not.
_MIN_MODEL_BYTES = {
    "tiny": 55_000_000,      # ~75MB complete
    "base": 115_000_000,     # ~145MB complete
    "small": 380_000_000,    # ~484MB complete
    "medium": 1_200_000_000,
    "large": 2_400_000_000,
}


def _min_model_bytes(model_name: str) -> int:
    size = model_name.split(".")[0].split("-")[0]
    return _MIN_MODEL_BYTES.get(size, 30_000_000)


def model_cached(model_name: str | None = None) -> bool:
    """Is the model already on disk? Answers without loading or downloading it.

    Connections needs this to show "downloaded" without paying a 1-3s load, and
    the test suite needs it so a fresh clone does not pull 145MB mid-run.
    """
    name = model_name or configured_model()
    repo = os.path.join(_hf_cache_dir(), f"models--Systran--faster-whisper-{name}")
    snapshots = os.path.join(repo, "snapshots")
    if not os.path.isdir(snapshots):
        return False

    # An interrupted download leaves a partial blob behind, and the snapshot can
    # still hold a model.bin symlink pointing straight at it. Presence of the
    # file is therefore not proof of a usable model — this is a fast heuristic,
    # and load_model() remains the authority.
    blobs = os.path.join(repo, "blobs")
    try:
        if any(f.endswith(".incomplete") for f in os.listdir(blobs)):
            return False
    except OSError:
        pass

    for entry in os.listdir(snapshots):
        model_bin = os.path.join(snapshots, entry, "model.bin")
        if not os.path.isfile(model_bin):
            continue
        # Compare against what this particular model should weigh. A flat floor
        # is not enough: the interrupted base.en stub that exposed this was
        # 67MB, which is larger than a *complete* tiny.en.
        try:
            if os.path.getsize(model_bin) < _min_model_bytes(name):
                return False
        except OSError:
            return False
        return True
    return False


def _write_status(**fields: Any) -> dict[str, Any]:
    path = _status_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    cur = _read_status()
    cur.update(fields)
    cur["updated_at"] = _utc_now()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cur, f, indent=2)
    os.replace(tmp, path)
    return cur


def _read_status() -> dict[str, Any]:
    data: dict[str, Any] = {
        "phase": "idle",
        "message": "",
        "model": configured_model(),
        "error": None,
        "updated_at": None,
    }
    path = _status_path()
    if os.path.isfile(path):
        try:
            raw = json.loads(open(path, encoding="utf-8").read())
            if isinstance(raw, dict):
                data.update(raw)
        except Exception:
            pass
    return data


def voice_status() -> dict[str, Any]:
    """What Connections and the voice console poll. Never raises."""
    status = _read_status()
    have_lib = library_available()
    status["library_installed"] = have_lib
    status["model_loaded"] = _model is not None
    status["model_downloaded"] = have_lib and model_cached(status.get("model"))
    status["available"] = have_lib and (_model is not None or status["model_downloaded"])
    # A model that failed to load is not available however complete it looks on
    # disk. Without this the setup card says "Ready" while every utterance
    # fails — the worst version of this bug, because it points the user away
    # from the actual problem.
    if status.get("phase") == "error" and _model is None:
        status["available"] = False
        status.setdefault("reason", status.get("error") or "The speech model failed to load.")
    if not have_lib:
        status["reason"] = (
            "Speech recognition isn't installed yet. Open Connections and turn on Voice."
        )
    return status


def load_model(model_name: str | None = None):
    """Return the warm model, loading it once. Raises if the library is absent."""
    global _model, _model_name

    name = model_name or configured_model()
    with _lock:
        if _model is not None and _model_name == name:
            return _model
        from faster_whisper import WhisperModel

        logger.info("loading whisper model %s (%s)", name, COMPUTE_TYPE)
        _write_status(phase="loading", message=f"Loading {name}…", model=name, error=None)
        _model = WhisperModel(name, device="cpu", compute_type=COMPUTE_TYPE)
        _model_name = name
        _write_status(phase="ready", message=f"{name} ready.", model=name, error=None)
        return _model


def transcribe(samples, *, sample_rate: int = SAMPLE_RATE) -> dict[str, Any]:
    """Transcribe mono float32 PCM. Returns ``{text, available, ...}``.

    A missing library is a setup state, not a crash — the console shows the
    reason and points at Connections.
    """
    if not library_available():
        return {"available": False, "text": "", "reason": voice_status()["reason"]}

    try:
        model = load_model()
    except Exception as e:
        logger.warning("whisper load failed: %s", e)
        _write_status(phase="error", error=str(e)[:500])
        return {"available": False, "text": "", "reason": f"Could not load the speech model: {e}"}

    try:
        segments, info = model.transcribe(
            samples,
            language="en",
            # The utterance is already endpointed by Silero in the browser, so
            # a second VAD pass here would only clip the start of short words.
            vad_filter=False,
            beam_size=1,          # greedy: this is a command, not a transcript
            condition_on_previous_text=False,
            # Bias the decoder toward the words that decide routing — the
            # product name, the command verbs, and the user's own employers.
            # See voice/vocabulary.py for what real speech does to them
            # unprompted.
            #
            # Note: initial_prompt was tried first and is worse than nothing —
            # the model treats the prompt as already spoken and omits the wake
            # phrase from its output ("Hey Shortlistr, open my tracker" became
            # "Open My Tracker"), which makes a command indistinguishable from
            # ambient speech.
            hotwords=vocabulary.hotwords(),
        )
        text = " ".join(s.text.strip() for s in segments).strip()
    except Exception as e:
        logger.warning("transcription failed: %s", e)
        return {"available": True, "text": "", "reason": str(e)}

    return {
        "available": True,
        "text": text,
        "duration": getattr(info, "duration", None),
        "model": _model_name,
    }


def ensure_voice_async(model: str | None = None) -> dict[str, Any]:
    """Kick off a background model download; the dashboard polls voice_status()."""
    global _ensure_thread

    if not library_available():
        return voice_status()
    if _ensure_thread and _ensure_thread.is_alive():
        return voice_status()

    def work() -> None:
        try:
            load_model(model)
        except Exception as e:
            logger.warning("voice ensure failed: %s", e)
            _write_status(phase="error", error=str(e)[:500], message="Setup failed.")

    _write_status(phase="downloading", message="Fetching the speech model…", error=None)
    _ensure_thread = threading.Thread(target=work, name="voice-ensure", daemon=True)
    _ensure_thread.start()
    return voice_status()
