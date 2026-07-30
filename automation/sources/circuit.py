"""Per-source circuit breaker — auto-disable after repeated failures."""

from __future__ import annotations

import json
import os
import time

from config import DATA_DIR

STATE_PATH = os.path.join(DATA_DIR, "source_circuits.json")
FAILURE_THRESHOLD = 5
OPEN_SECONDS = 86400  # 24h


def _load() -> dict:
    if not os.path.exists(STATE_PATH):
        return {}
    try:
        return json.load(open(STATE_PATH, encoding="utf-8"))
    except Exception:
        return {}


def _save(state: dict) -> None:
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    json.dump(state, open(STATE_PATH, "w", encoding="utf-8"), indent=2)


def is_open(name: str) -> bool:
    state = _load()
    entry = state.get(name, {})
    if not entry.get("open"):
        return False
    opened_at = entry.get("opened_at", 0)
    if time.time() - opened_at > OPEN_SECONDS:
        entry["open"] = False
        entry["failures"] = 0
        state[name] = entry
        _save(state)
        return False
    return True


def record_success(name: str) -> None:
    state = _load()
    state[name] = {"open": False, "failures": 0, "opened_at": 0}
    _save(state)


def record_failure(name: str) -> None:
    state = _load()
    entry = state.get(name, {"failures": 0, "open": False, "opened_at": 0})
    entry["failures"] = entry.get("failures", 0) + 1
    if entry["failures"] >= FAILURE_THRESHOLD:
        entry["open"] = True
        entry["opened_at"] = time.time()
    state[name] = entry
    _save(state)


def all_status() -> dict[str, dict]:
    return _load()
