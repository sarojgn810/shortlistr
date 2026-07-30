"""Detect machine capacity and recommend Local AI models that fit.

Used by Connections before/during Local AI setup so a non-technical user sees
what will run smoothly on *their* laptop — not a one-size-fits-all guess.
"""

from __future__ import annotations

import os
import platform
import re
import subprocess
from typing import Any

# Catalog: min_ram_gb is a soft floor for "smooth" CPU inference (GGUF Q4-ish).
# download_mb is approximate pull size for Ollama tags.
MODEL_CATALOG: list[dict[str, Any]] = [
    {
        "id": "qwen2.5:0.5b",
        "name": "Qwen 2.5 · 0.5B",
        "min_ram_gb": 4,
        "download_mb": 400,
        "quality": "Good for scoring & short cover letters",
        "speed": "Fastest",
    },
    {
        "id": "qwen2.5:1.5b",
        "name": "Qwen 2.5 · 1.5B",
        "min_ram_gb": 8,
        "download_mb": 1000,
        "quality": "Better writing, still light",
        "speed": "Comfortable on most laptops",
    },
    {
        "id": "gemma2:2b",
        "name": "Gemma 2 · 2B",
        "min_ram_gb": 10,
        "download_mb": 1600,
        "quality": "Stronger reasoning for A–G notes",
        "speed": "Fine on 16 GB machines",
    },
    {
        "id": "llama3.2:3b",
        "name": "Llama 3.2 · 3B",
        "min_ram_gb": 12,
        "download_mb": 2000,
        "quality": "Best local quality we recommend",
        "speed": "Needs headroom — may feel slow on 8 GB",
    },
]


def _ram_gb() -> float | None:
    """Best-effort total physical RAM in GiB."""
    try:
        if platform.system() == "Darwin":
            out = subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True, timeout=5)
            return round(int(out.strip()) / (1024**3), 1)
        if platform.system() == "Linux":
            with open("/proc/meminfo", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        kb = int(re.findall(r"\d+", line)[0])
                        return round(kb / (1024**2), 1)
        if platform.system() == "Windows":
            out = subprocess.check_output(
                ["wmic", "ComputerSystem", "get", "TotalPhysicalMemory"],
                text=True,
                timeout=10,
            )
            for tok in out.split():
                if tok.isdigit():
                    return round(int(tok) / (1024**3), 1)
    except Exception:
        pass
    # psutil is optional
    try:
        import psutil  # type: ignore

        return round(psutil.virtual_memory().total / (1024**3), 1)
    except Exception:
        return None


def _cpu_count() -> int:
    return os.cpu_count() or 2


def _tier(ram_gb: float | None, cpus: int) -> str:
    """low | mid | high — drives default model pick."""
    ram = ram_gb if ram_gb is not None else 8.0
    if ram < 7.5 or cpus <= 2:
        return "low"
    if ram < 14 or cpus <= 4:
        return "mid"
    return "high"


def _fit_for(model: dict[str, Any], ram_gb: float | None) -> str:
    """smooth | tight | heavy"""
    need = float(model["min_ram_gb"])
    ram = ram_gb if ram_gb is not None else 8.0
    # Leave ~2–3 GB for OS + Shortlistr + browser
    usable = ram - 2.5
    if usable >= need + 2:
        return "smooth"
    if usable >= need:
        return "tight"
    return "heavy"


def detect_system() -> dict[str, Any]:
    ram = _ram_gb()
    cpus = _cpu_count()
    system = platform.system()
    machine = platform.machine() or ""
    tier = _tier(ram, cpus)
    return {
        "os": system,
        "os_label": {
            "Darwin": "Mac",
            "Windows": "Windows",
            "Linux": "Linux",
        }.get(system, system or "Unknown"),
        "arch": machine,
        "ram_gb": ram,
        "cpu_cores": cpus,
        "tier": tier,
        "tier_label": {
            "low": "Modest laptop — keep the model tiny",
            "mid": "Typical laptop — a small model runs well",
            "high": "Comfortable machine — you can pick a stronger model",
        }[tier],
        "summary": _summary(ram, cpus, system, tier),
    }


def _summary(ram_gb: float | None, cpus: int, system: str, tier: str) -> str:
    os_label = {"Darwin": "Mac", "Windows": "Windows", "Linux": "Linux"}.get(system, system)
    ram_bit = f"{ram_gb:g} GB RAM" if ram_gb is not None else "RAM unknown"
    return f"{os_label} · {ram_bit} · {cpus} CPU cores — { {'low': 'best with the smallest model', 'mid': 'good for 0.5B–1.5B', 'high': 'can run up to ~3B locally'}[tier] }"


def recommend_models(system: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    sysinfo = system or detect_system()
    ram = sysinfo.get("ram_gb")
    out: list[dict[str, Any]] = []
    for m in MODEL_CATALOG:
        fit = _fit_for(m, ram if isinstance(ram, (int, float)) else None)
        out.append(
            {
                **m,
                "fit": fit,
                "fit_label": {
                    "smooth": "Recommended — should run smoothly",
                    "tight": "Possible — may feel slow under load",
                    "heavy": "Not recommended — likely to struggle or swap",
                }[fit],
                "recommended": False,
            }
        )
    # Pick the strongest "smooth" model; else the lightest overall.
    smooth = [x for x in out if x["fit"] == "smooth"]
    pick = smooth[-1] if smooth else out[0]
    for x in out:
        x["recommended"] = x["id"] == pick["id"]
    return out


def recommended_model_id(system: dict[str, Any] | None = None) -> str:
    for m in recommend_models(system):
        if m.get("recommended"):
            return str(m["id"])
    return str(MODEL_CATALOG[0]["id"])


def setup_guide(system: dict[str, Any] | None = None, *, model_id: str | None = None) -> list[dict[str, str]]:
    """Plain-language steps for the Connections UI."""
    sysinfo = system or detect_system()
    model = model_id or recommended_model_id(sysinfo)
    os_name = sysinfo.get("os") or platform.system()
    steps: list[dict[str, str]] = [
        {
            "title": "We checked this computer",
            "body": str(sysinfo.get("summary") or ""),
        },
        {
            "title": "Pick a model that fits",
            "body": f"We suggest {model} for your machine. You can choose another option below if you prefer.",
        },
    ]
    if os_name == "Windows":
        steps.append(
            {
                "title": "Install the Local AI app (Windows)",
                "body": "If setup can’t finish automatically, download Ollama from ollama.com/download, open it once, then come back and press Set up Local AI again.",
            }
        )
    elif os_name == "Darwin":
        steps.append(
            {
                "title": "Install the Local AI helper (Mac)",
                "body": "Shortlistr tries to install Ollama for you. If macOS asks for permission, allow it. You can also install Ollama from ollama.com once, then return here.",
            }
        )
    else:
        steps.append(
            {
                "title": "Install the Local AI helper (Linux)",
                "body": "Shortlistr runs the official Ollama installer when needed. You may be asked for your password once.",
            }
        )
    steps.extend(
        [
            {
                "title": "Download the model (one time)",
                "body": f"Press Set up Local AI. The first download stays on this computer (~minutes). Leave this page open.",
            },
            {
                "title": "You’re done",
                "body": "When status says Ready, scoring and cover letters use Local AI automatically. No API key required.",
            },
        ]
    )
    return steps


def capability_report() -> dict[str, Any]:
    system = detect_system()
    models = recommend_models(system)
    rec = recommended_model_id(system)
    return {
        "system": system,
        "models": models,
        "recommended_model": rec,
        "guide": setup_guide(system, model_id=rec),
    }
