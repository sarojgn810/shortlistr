"""Back-compat for installs that predate the Autojob -> Shortlistr rename.

An existing user has AUTOJOB_* in their .env and their whole job history in
data/autojob.db. Every assertion here is about not stranding them: a rename that
silently loses somebody's LLM key or shows them an empty inbox is data loss as
far as they are concerned, whatever the file system says.
"""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))


# ── env names ────────────────────────────────────────────────────────────────

def test_legacy_env_var_is_adopted_under_the_new_name(monkeypatch):
    import config

    monkeypatch.delenv("SHORTLISTR_TEST_SECRET", raising=False)
    monkeypatch.setenv("AUTOJOB_TEST_SECRET", "from-legacy")
    config._adopt_legacy_env()
    assert os.environ["SHORTLISTR_TEST_SECRET"] == "from-legacy"


def test_new_env_var_wins_over_legacy(monkeypatch):
    """Adoption must never overwrite a value the user has already migrated."""
    import config

    monkeypatch.setenv("AUTOJOB_TEST_SECRET", "old")
    monkeypatch.setenv("SHORTLISTR_TEST_SECRET", "new")
    config._adopt_legacy_env()
    assert os.environ["SHORTLISTR_TEST_SECRET"] == "new"


def test_adoption_does_not_invent_unrelated_vars(monkeypatch):
    import config

    monkeypatch.delenv("SHORTLISTR_NOT_A_REAL_VAR", raising=False)
    config._adopt_legacy_env()
    assert "SHORTLISTR_NOT_A_REAL_VAR" not in os.environ


# ── secrets ──────────────────────────────────────────────────────────────────

def test_get_secret_falls_back_to_the_legacy_name(monkeypatch):
    """The keychain is disabled under pytest, so this exercises the env path."""
    import secrets_store

    monkeypatch.delenv("SHORTLISTR_LLM_API_KEY", raising=False)
    monkeypatch.setenv("AUTOJOB_LLM_API_KEY", "gsk_legacy_key")
    assert secrets_store.get_secret("SHORTLISTR_LLM_API_KEY") == "gsk_legacy_key"


def test_get_secret_prefers_the_new_name(monkeypatch):
    import secrets_store

    monkeypatch.setenv("AUTOJOB_LLM_API_KEY", "gsk_old")
    monkeypatch.setenv("SHORTLISTR_LLM_API_KEY", "gsk_new")
    assert secrets_store.get_secret("SHORTLISTR_LLM_API_KEY") == "gsk_new"


def test_legacy_secret_names_are_migrated_from_env_file(monkeypatch, tmp_path):
    """A pre-rename .env line is recognised as a known secret worth migrating."""
    import secrets_store

    assert "AUTOJOB_LLM_API_KEY" in secrets_store.KNOWN_SECRETS
    assert "SHORTLISTR_LLM_API_KEY" in secrets_store.KNOWN_SECRETS


# ── the database ─────────────────────────────────────────────────────────────

def _make_db(path: str, jobs: int) -> None:
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE jobs (id TEXT)")
    conn.executemany("INSERT INTO jobs VALUES (?)", [(f"j{i}",) for i in range(jobs)])
    conn.commit()
    conn.close()


def test_legacy_database_is_adopted(monkeypatch):
    """autojob.db becomes shortlistr.db instead of being ignored beside it."""
    import store.db as db_mod

    tmp = tempfile.mkdtemp()
    legacy = os.path.join(tmp, "autojob.db")
    new = os.path.join(tmp, "shortlistr.db")
    _make_db(legacy, 7)

    monkeypatch.setattr(db_mod, "DB_PATH", new)
    monkeypatch.setattr(db_mod, "LEGACY_DB_PATH", legacy)

    assert db_mod.active_db_path() == new
    assert os.path.exists(new)
    assert not os.path.exists(legacy)
    assert sqlite3.connect(new).execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 7


def test_adoption_never_clobbers_an_existing_database(monkeypatch):
    """If both exist, the new file is authoritative and the legacy one is left alone."""
    import store.db as db_mod

    tmp = tempfile.mkdtemp()
    legacy = os.path.join(tmp, "autojob.db")
    new = os.path.join(tmp, "shortlistr.db")
    _make_db(legacy, 3)
    _make_db(new, 99)

    monkeypatch.setattr(db_mod, "DB_PATH", new)
    monkeypatch.setattr(db_mod, "LEGACY_DB_PATH", legacy)

    assert db_mod.active_db_path() == new
    assert sqlite3.connect(new).execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 99
    assert os.path.exists(legacy)


def test_no_legacy_database_is_a_clean_first_run(monkeypatch):
    import store.db as db_mod

    tmp = tempfile.mkdtemp()
    new = os.path.join(tmp, "shortlistr.db")
    monkeypatch.setattr(db_mod, "DB_PATH", new)
    monkeypatch.setattr(db_mod, "LEGACY_DB_PATH", os.path.join(tmp, "autojob.db"))

    assert db_mod.active_db_path() == new
    assert not os.path.exists(new)  # resolving a path must not create the file


# ── the referral desk is gone ────────────────────────────────────────────────

@pytest.mark.parametrize("table", ["referrals", "referrers", "engage_sessions",
                                   "telegram_links"])
def test_referral_tables_are_dropped_by_v17(monkeypatch, table):
    import store.db as db_mod

    tmp = tempfile.mkdtemp()
    monkeypatch.setattr(db_mod, "DATA_DIR", tmp)
    monkeypatch.setattr(db_mod, "DB_PATH", os.path.join(tmp, "shortlistr.db"))
    monkeypatch.setattr(db_mod, "LEGACY_DB_PATH", os.path.join(tmp, "autojob.db"))
    db_mod.init_db()

    with db_mod.db() as conn:
        found = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name = ?", (table,)
        ).fetchone()
    assert found is None, f"{table} should not survive the v17 migration"


def test_no_platform_scope_remains():
    """The two-database scope switch is gone; nothing should reintroduce it."""
    import store.db as db_mod

    for gone in ("using_platform_db", "platform_db", "platform_db_path",
                 "is_platform_scope"):
        assert not hasattr(db_mod, gone), f"{gone} came back"
