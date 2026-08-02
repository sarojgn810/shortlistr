"""Local AI bootstrap — tiny Ollama model, no terminal for the user.

Goal: a non-technical first run can get on-device scoring without pasting an
API key. We install/start Ollama when possible, pull a small Instruct model
(~0.5B), then ``provider: auto`` prefers that local path.

Heavy work runs in a background thread; the dashboard polls ``local_ai_status``.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import shutil
import subprocess
import threading
import time
from datetime import datetime, timezone
from typing import Any

import requests

logger = logging.getLogger(__name__)

# Fallback if hardware probe fails — still safe on ~8 GB RAM / CPU-only.
RECOMMENDED_MODEL = "qwen2.5:0.5b"
DEFAULT_OLLAMA_URL = "http://localhost:11434"

_lock = threading.Lock()
_ensure_thread: threading.Thread | None = None


def _data_dir() -> str:
    try:
        from config import DATA_DIR

        return DATA_DIR
    except Exception:
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        return os.path.join(root, "data")


def _status_path() -> str:
    return os.path.join(_data_dir(), "local_ai_status.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _strip_ansi(text: str) -> str:
    """Ollama/brew/winget stderr often includes terminal escape codes."""
    import re

    return re.sub(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\].*?\x07", "", text or "").strip()


def _write_status(**fields: Any) -> dict[str, Any]:
    path = _status_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    cur = local_ai_status()
    cur.update(fields)
    if isinstance(cur.get("error"), str):
        cur["error"] = _strip_ansi(cur["error"])[-500:] or None
    if isinstance(cur.get("message"), str):
        cur["message"] = _strip_ansi(cur["message"])[-500:]
    cur["updated_at"] = _utc_now()
    cur.setdefault("model", RECOMMENDED_MODEL)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cur, f, indent=2)
    os.replace(tmp, path)
    return cur


def _default_model() -> str:
    try:
        from llm.hardware import recommended_model_id

        return recommended_model_id()
    except Exception:
        return RECOMMENDED_MODEL


def local_ai_status() -> dict[str, Any]:
    """Persisted + live probe — safe for the Connections UI."""
    path = _status_path()
    default_model = _default_model()
    data: dict[str, Any] = {
        "phase": "idle",
        "message": "",
        "model": default_model,
        "ollama_installed": False,
        "ollama_running": False,
        "model_ready": False,
        "ready": False,
        "error": None,
        "updated_at": None,
    }
    if os.path.isfile(path):
        try:
            raw = json.loads(open(path, encoding="utf-8").read())
            if isinstance(raw, dict):
                data.update({k: raw[k] for k in raw if k in data or k in ("phase", "message", "error", "updated_at", "model")})
                if isinstance(data.get("error"), str):
                    data["error"] = _strip_ansi(data["error"])[-500:] or None
                if isinstance(data.get("message"), str):
                    data["message"] = _strip_ansi(data["message"])[-500:]
        except Exception:
            pass

    url = DEFAULT_OLLAMA_URL
    try:
        from config import LLM_CONFIG

        url = str(LLM_CONFIG.get("ollama_url") or url)
    except Exception:
        pass

    data["ollama_installed"] = bool(shutil.which("ollama"))
    data["ollama_running"] = _ollama_reachable(url)
    wanted = str(data.get("model") or RECOMMENDED_MODEL)
    was_ready = bool(data.get("model_ready"))
    present = _model_present(url, wanted) if data["ollama_running"] else False
    if present is None:
        # Ollama did not answer in time — almost always because it is busy
        # loading. Keep what we last knew rather than telling the user their
        # setup vanished.
        data["model_ready"] = was_ready
        data["probe_unavailable"] = True
    else:
        data["model_ready"] = bool(present)
    if not data["model_ready"] and data["ollama_running"] and present is not None:
        # The recommended tag is a suggestion. Someone already holding
        # gemma3:12b should not be told Local AI is unavailable because a 3B
        # download failed — adopt what is pulled and say which one.
        adopted = usable_local_model(url)
        if adopted:
            data["model"] = adopted
            data["model_ready"] = True
            data["adopted_installed_model"] = adopted
            data["phase"] = "ready"
            data["error"] = None
            data["message"] = f"Local AI ready (using installed {adopted})"
    data["ready"] = bool(data["model_ready"])
    if data["ready"] and data.get("phase") not in ("error", "installing", "pulling", "starting"):
        data["phase"] = "ready"
        data["message"] = f"Local AI ready ({data.get('model') or default_model})"
        data["error"] = None
    elif (
        not data["ready"]
        and data.get("phase") == "ready"
        and not data.get("probe_unavailable")
    ):
        # Phase used to only ever move up, so a model that was removed left the
        # card claiming "ready" while nothing worked. Only downgrade when Ollama
        # actually answered — a timed-out probe means unknown, not gone.
        data["phase"] = "idle"
        data["message"] = "Local AI is not set up on this computer yet"
    try:
        from llm.hardware import capability_report

        cap = capability_report()
        data["capability"] = cap
        if not data.get("model"):
            data["model"] = cap.get("recommended_model") or default_model
    except Exception as e:
        data["capability"] = {"error": str(e)[:200]}
    return data


def is_local_ready(base_url: str | None = None, model: str | None = None) -> bool:
    url = (base_url or DEFAULT_OLLAMA_URL).rstrip("/")
    mod = model or _default_model()
    return _ollama_reachable(url) and _model_present(url, mod)


def _ollama_reachable(base_url: str) -> bool:
    try:
        r = requests.get(f"{base_url.rstrip('/')}/api/tags", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def installed_models(base_url: str | None = None) -> list[tuple[str, int]]:
    """(tag, size_bytes) for every model Ollama has pulled, largest first."""
    url = (base_url or DEFAULT_OLLAMA_URL).rstrip("/")
    try:
        r = requests.get(f"{url}/api/tags", timeout=5)
        r.raise_for_status()
        rows = (r.json() or {}).get("models") or []
    except Exception:
        return []
    out = [(str(m.get("name") or ""), int(m.get("size") or 0)) for m in rows if m.get("name")]
    out.sort(key=lambda t: t[1], reverse=True)
    return out


# Tags that are not general chat models, so picking one would look "ready" and
# then fail on the first evaluation.
_NOT_CHAT = ("embed", "embedding", "rerank", "moondream", "llava", "clip",
             "whisper", "coder-base", "sd-", "stable-diffusion")


# hardware.py sizes a 3B model (~2GB of weights) at a 12GB machine — roughly a
# 1:6 ratio, because the user still has a browser and an editor open. Sizing by
# "weights plus a bit" instead picked an 8.1GB gemma3:12b on an 18GB laptop,
# which Ollama refused to load with "model failed to load, this may be due to
# resource limitations". Keep the ratio the rest of the project already uses.
_RAM_PER_WEIGHT_BYTE = 4.0


def usable_local_model(base_url: str | None = None) -> str:
    """The best already-pulled model this machine can actually load, or "".

    The recommended tag is a suggestion, not a requirement: someone already
    holding a capable model should not be told Local AI is unavailable because a
    different download failed.

    But bigger is not automatically better — picking the largest pulled model
    got "model failed to load, this may be due to resource limitations" from an
    8.1GB gemma3:12b. So the largest that *fits* wins, judged against total RAM
    rather than free RAM: momentary pressure comes and goes, and a model that
    fits the machine is still the right default once a browser closes.
    """
    try:
        from llm.hardware import detect_system

        ram_gb = float((detect_system() or {}).get("ram_gb") or 0)
    except Exception:
        ram_gb = 0.0
    budget = (ram_gb * 1e9 / _RAM_PER_WEIGHT_BYTE) if ram_gb > 0 else 0

    for name, size in installed_models(base_url):
        if any(bad in name.lower() for bad in _NOT_CHAT):
            continue
        if budget and size and size > budget:
            continue
        return name
    return ""


def _model_present(base_url: str, model: str) -> bool | None:
    """True/False when Ollama answers, None when it could not be asked.

    These are different facts and collapsing them made the Connections card
    flicker: while Ollama is busy pulling or loading a model it stops answering
    /api/tags within the timeout, the probe returned False, and a card that said
    "ready" a second ago reverted to "set up Local AI". Callers keep the last
    known state when the answer is None instead of downgrading on a timeout.
    """
    try:
        r = requests.get(f"{base_url.rstrip('/')}/api/tags", timeout=5)
        r.raise_for_status()
        want = model.strip().lower()
        for m in (r.json() or {}).get("models") or []:
            name = str(m.get("name") or "").lower()
            if not name:
                continue
            if name == want or name.startswith(want + "-") or name.startswith(want + ":"):
                return True
            # "qwen2.5:0.5b" matches "qwen2.5:0.5b-instruct-q4_K_M" style tags
            if want in name:
                return True
        return False
    except Exception:
        return None


def _start_ollama_serve() -> bool:
    """Best-effort: launch ``ollama serve`` in the background if the CLI exists."""
    if not shutil.which("ollama"):
        return False
    try:
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception as e:
        logger.warning("Could not start ollama serve: %s", e)
        return False
    for _ in range(20):
        time.sleep(0.5)
        if _ollama_reachable(DEFAULT_OLLAMA_URL):
            return True
    return _ollama_reachable(DEFAULT_OLLAMA_URL)


def _install_ollama() -> tuple[bool, str]:
    """Try a silent Ollama install. Returns (ok, message)."""
    if shutil.which("ollama"):
        return True, "Ollama already installed"

    system = platform.system()
    if system == "Darwin" and shutil.which("brew"):
        _write_status(phase="installing", message="Installing Ollama with Homebrew…", error=None)
        try:
            r = subprocess.run(
                ["brew", "install", "ollama"],
                capture_output=True,
                text=True,
                timeout=600,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return False, "Installing Ollama timed out"
        if r.returncode != 0 and not shutil.which("ollama"):
            err = (r.stderr or r.stdout or "brew install failed").strip()
            return False, err[-400:]
        if shutil.which("ollama"):
            return True, "Ollama installed via Homebrew"

    if system in ("Linux", "Darwin"):
        _write_status(
            phase="installing",
            message="Downloading Ollama…",
            error=None,
        )
        # Official installer — may need network; no terminal for the user.
        try:
            r = subprocess.run(
                ["bash", "-c", "curl -fsSL https://ollama.com/install.sh | sh"],
                capture_output=True,
                text=True,
                timeout=600,
                check=False,
            )
        except FileNotFoundError:
            return False, "Cannot install Ollama automatically on this system"
        except subprocess.TimeoutExpired:
            return False, "Ollama install timed out"
        if shutil.which("ollama"):
            return True, "Ollama installed"
        err = (r.stderr or r.stdout or "install script failed").strip()
        return False, err[-400:] or "Ollama install failed"

    if system == "Windows":
        # Prefer winget so a second laptop doesn't depend on a browser download.
        if shutil.which("winget"):
            _write_status(
                phase="installing",
                message="Installing Ollama with winget…",
                error=None,
            )
            try:
                r = subprocess.run(
                    [
                        "winget",
                        "install",
                        "-e",
                        "--id",
                        "Ollama.Ollama",
                        "--accept-package-agreements",
                        "--accept-source-agreements",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=900,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                return False, "Installing Ollama with winget timed out"
            # Refresh PATH for this process if possible
            if shutil.which("ollama"):
                return True, "Ollama installed via winget"
            # winget often succeeds but PATH needs a new shell — try common path
            for candidate in (
                os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe"),
                r"C:\Program Files\Ollama\ollama.exe",
            ):
                if os.path.isfile(candidate):
                    os.environ["PATH"] = (
                        os.path.dirname(candidate) + os.pathsep + os.environ.get("PATH", "")
                    )
                    if shutil.which("ollama") or os.path.isfile(candidate):
                        return True, "Ollama installed via winget"
            err = (r.stderr or r.stdout or "winget install finished").strip()
            return (
                False,
                "Ollama may be installed — open the Ollama app once, then click Set up Local AI again. "
                + (err[-200:] if err else ""),
            )
        return (
            False,
            "Install Ollama from https://ollama.com/download (Windows), open the app once, "
            "then click Set up Local AI again. Or paste a free Groq API key on Connections for cloud scoring.",
        )

    return False, f"Automatic Ollama install is not supported on {system}"


def _pull_model(base_url: str, model: str) -> tuple[bool, str]:
    _write_status(phase="pulling", message=f"Downloading {model} (one-time, stays on this computer)…", error=None)
    # Prefer CLI — streams progress in ollama; HTTP pull also works.
    if shutil.which("ollama"):
        try:
            r = subprocess.run(
                ["ollama", "pull", model],
                capture_output=True,
                text=True,
                timeout=1800,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return False, f"Downloading {model} timed out"
        if r.returncode == 0 or _model_present(base_url, model):
            return True, f"Model {model} ready"
        err = (r.stderr or r.stdout or "pull failed").strip()
        return False, err[-400:]

    try:
        with requests.post(
            f"{base_url.rstrip('/')}/api/pull",
            json={"name": model, "stream": False},
            timeout=1800,
        ) as resp:
            if resp.status_code == 200 and _model_present(base_url, model):
                return True, f"Model {model} ready"
            return False, (resp.text or f"pull HTTP {resp.status_code}")[:400]
    except Exception as e:
        return False, str(e)[:400]


def _activate_local_in_profile(model: str) -> None:
    """Point profile at Local AI without wiping a deliberate cloud choice.

    Only flips ``none`` / ``auto`` / ``ollama`` / empty → ``auto`` + model.
    Patches YAML in place so we don't require a finished onboarding profile.
    """
    try:
        from config import PROFILE_PATH
    except Exception:
        return
    if not os.path.isfile(PROFILE_PATH):
        return
    try:
        lines = open(PROFILE_PATH, encoding="utf-8").read().splitlines(keepends=True)
    except OSError:
        return

    in_llm = False
    current = "none"
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("llm:"):
            in_llm = True
            continue
        if in_llm and stripped and not stripped.startswith("#") and not line[:1].isspace() and ":" in stripped:
            in_llm = False
        if in_llm and stripped.startswith("provider:"):
            current = stripped.split(":", 1)[1].strip().strip('"').strip("'").lower()
            break
    if current not in ("", "none", "auto", "ollama"):
        return

    in_llm = False
    saw_llm = False
    saw_provider = False
    saw_model = False
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("llm:"):
            in_llm = True
            saw_llm = True
            out.append(line)
            continue
        if in_llm and stripped and not stripped.startswith("#") and not line[:1].isspace() and ":" in stripped:
            in_llm = False
        if in_llm and stripped.startswith("provider:"):
            indent = line[: len(line) - len(line.lstrip())]
            out.append(f'{indent}provider: "auto"\n')
            saw_provider = True
            continue
        if in_llm and stripped.startswith("model:"):
            indent = line[: len(line) - len(line.lstrip())]
            out.append(f'{indent}model: "{model}"\n')
            saw_model = True
            continue
        out.append(line)

    if not saw_llm:
        out.append("\nllm:\n")
        out.append('  provider: "auto"\n')
        out.append(f'  model: "{model}"\n')
        out.append('  api_key: ""\n')
        out.append('  ollama_url: "http://localhost:11434"\n')
    elif not saw_provider or not saw_model:
        # Inject missing keys right after `llm:`
        injected: list[str] = []
        for line in out:
            injected.append(line)
            if line.strip().startswith("llm:") and not saw_provider:
                injected.append('  provider: "auto"\n')
                saw_provider = True
                if not saw_model:
                    injected.append(f'  model: "{model}"\n')
                    saw_model = True
        out = injected

    try:
        with open(PROFILE_PATH, "w", encoding="utf-8") as f:
            f.writelines(out)
            if out and not out[-1].endswith("\n"):
                f.write("\n")
    except OSError as e:
        logger.warning("Could not write Local AI into profile: %s", e)
        return
    try:
        from llm import reload_llm_config

        reload_llm_config()
    except Exception:
        pass


def ensure_local_ai(*, force: bool = False, model: str | None = None) -> dict[str, Any]:
    """Install/start Ollama and pull the chosen/recommended model. Blocking.

    Safe to call from a worker thread. Concurrent callers share one run via lock.
    """
    with _lock:
        st = local_ai_status()
        if st.get("ready") and not force and (
            not model or str(st.get("model") or "") == model
        ):
            return _write_status(
                phase="ready",
                message=st.get("message") or "Local AI ready",
                error=None,
            )

        chosen = (model or "").strip() or _default_model()
        try:
            from llm.hardware import MODEL_CATALOG

            allowed = {str(m["id"]) for m in MODEL_CATALOG}
            if chosen not in allowed:
                # Allow simple ollama tags like "name:tag"
                if not (":" in chosen and " " not in chosen and len(chosen) < 64):
                    chosen = _default_model()
        except Exception:
            pass

        url = DEFAULT_OLLAMA_URL
        try:
            from config import LLM_CONFIG

            url = str(LLM_CONFIG.get("ollama_url") or url)
        except Exception:
            pass

        use_model = chosen
        _write_status(
            phase="starting",
            message=f"Preparing {use_model}…",
            error=None,
            model=use_model,
        )

        if not shutil.which("ollama"):
            ok, msg = _install_ollama()
            if not ok:
                return _write_status(phase="error", message=msg, error=msg, model=use_model)

        if not _ollama_reachable(url):
            _write_status(phase="starting", message="Starting Local AI…", error=None, model=use_model)
            if not _start_ollama_serve():
                msg = (
                    "Ollama is installed but not running. Open the Ollama app once, "
                    "then click Set up Local AI again."
                )
                return _write_status(phase="error", message=msg, error=msg, model=use_model)

        if not _model_present(url, use_model):
            ok, msg = _pull_model(url, use_model)
            if not ok:
                return _write_status(phase="error", message=msg, error=msg, model=use_model)

        _activate_local_in_profile(use_model)
        return _write_status(
            phase="ready",
            message=f"Local AI ready ({use_model})",
            error=None,
            model=use_model,
            ollama_installed=True,
            ollama_running=True,
            model_ready=True,
            ready=True,
        )


def ensure_local_ai_async(*, force: bool = False, model: str | None = None) -> dict[str, Any]:
    """Kick ensure in a daemon thread; return current status immediately."""
    global _ensure_thread
    st = local_ai_status()
    if st.get("ready") and not force and (
        not model or str(st.get("model") or "") == model
    ):
        return st
    if st.get("phase") in ("installing", "pulling", "starting") and _ensure_thread and _ensure_thread.is_alive():
        return st

    chosen = (model or "").strip() or None

    def _run() -> None:
        try:
            ensure_local_ai(force=force, model=chosen)
        except Exception as e:
            logger.exception("Local AI setup failed")
            _write_status(phase="error", message=str(e)[:400], error=str(e)[:400])

    with _lock:
        if _ensure_thread and _ensure_thread.is_alive() and not force:
            return local_ai_status()
        _write_status(
            phase="starting",
            message="Setting up Local AI on this computer…",
            error=None,
            model=chosen or st.get("model") or _default_model(),
        )
        _ensure_thread = threading.Thread(target=_run, daemon=True, name="local-ai-ensure")
        _ensure_thread.start()
    return local_ai_status()


def maybe_autostart_local_ai() -> None:
    """First-boot helper: probe hardware and surface Local AI status.

    Does **not** start a multi-hundred-MB download by itself — Connections shows
    capability + a step-by-step guide, then the user confirms Install. Set
    ``SHORTLISTR_LOCAL_AI_AUTOSTART=1`` to restore silent pull of the recommended model.
    """
    try:
        # Populate capability on the status payload for the dashboard.
        local_ai_status()
    except Exception:
        pass

    if os.environ.get("SHORTLISTR_LOCAL_AI_AUTOSTART", "").strip() not in ("1", "true", "yes"):
        return

    try:
        from config import LLM_CONFIG
        from secrets_store import get_secret

        provider = str(LLM_CONFIG.get("provider") or "none").lower().strip()
        if provider in ("anthropic", "openai", "gemini", "grok", "groq"):
            key = get_secret("SHORTLISTR_LLM_API_KEY", "")
            if key:
                return
        if provider not in ("", "none", "auto", "ollama"):
            return
    except Exception:
        pass

    if local_ai_status().get("ready"):
        return
    ensure_local_ai_async(force=False)
