"""Agent memory (learnings) + migration v4 tests."""

from __future__ import annotations

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))


def _isolate(monkeypatch):
    tmp = tempfile.mkdtemp()
    import config
    import store.db as db_mod

    monkeypatch.setattr(config, "DATA_DIR", tmp)
    monkeypatch.setattr(db_mod, "DATA_DIR", tmp)
    monkeypatch.setattr(db_mod, "DB_PATH", os.path.join(tmp, "shortlistr.db"))
    return tmp


def test_migration_creates_learnings_at_v4(monkeypatch):
    _isolate(monkeypatch)
    import store.db as db_mod

    db_mod.init_db()
    with db_mod.db() as conn:
        ver = conn.execute("SELECT version FROM schema_version").fetchone()["version"]
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(learnings)").fetchall()]
    assert ver >= 4
    assert {"insight", "confidence", "kind", "refs"} <= set(cols)


def test_add_and_search_learnings(monkeypatch):
    _isolate(monkeypatch)
    from memory import store as mem

    mem.add_learning("Fintech JDs score high but ghost", kind="pattern", key="fintech-ghost", confidence=7)
    mem.add_learning("CVs leading with MTTR get more replies", kind="outcome", key="mttr-cv", confidence=8)

    hits = mem.search_learnings("mttr")
    assert len(hits) == 1 and "MTTR" in hits[0]["insight"]

    all_recent = mem.search_learnings("")
    assert len(all_recent) == 2

    none = mem.search_learnings("kubernetes")
    assert none == []


def test_working_memory_roundtrip(monkeypatch):
    _isolate(monkeypatch)
    from memory import store as mem

    mem.set_working_memory({"task": "evaluate batch", "cursor": 3})
    assert mem.get_working_memory()["cursor"] == 3
