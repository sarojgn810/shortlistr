"""Secret store tests (run with keychain forced off → process-env fallback)."""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))


def test_set_get_has_delete_roundtrip(monkeypatch):
    import secrets_store as s

    monkeypatch.delenv("SHORTLISTR_TEST_SECRET", raising=False)
    assert s.has_secret("SHORTLISTR_TEST_SECRET") is False

    s.set_secret("SHORTLISTR_TEST_SECRET", "abc123")
    assert s.get_secret("SHORTLISTR_TEST_SECRET") == "abc123"
    assert s.has_secret("SHORTLISTR_TEST_SECRET") is True

    s.delete_secret("SHORTLISTR_TEST_SECRET")
    assert s.get_secret("SHORTLISTR_TEST_SECRET") == ""
    assert s.get_secret("SHORTLISTR_TEST_SECRET", "fallback") == "fallback"


def test_keyring_disabled_under_pytest():
    import secrets_store as s

    # PYTEST_CURRENT_TEST is set during tests → no real keychain is touched.
    assert s._keyring() is None


def test_migrate_is_idempotent_with_backend(tmp_path, monkeypatch):
    import secrets_store as s

    store: dict = {}

    class FakeKR:
        def set_password(self, svc, name, val):
            store[(svc, name)] = val

        def get_password(self, svc, name):
            return store.get((svc, name))

        def delete_password(self, svc, name):
            store.pop((svc, name), None)

    monkeypatch.setattr(s, "_keyring", lambda: FakeKR())
    env = tmp_path / ".env"
    env.write_text("SHORTLISTR_LLM_API_KEY=sk-real-123\nOTHER=keep\n")

    assert s.migrate_env_to_keyring(str(env)) == ["SHORTLISTR_LLM_API_KEY"]
    assert store[(s.SERVICE, "SHORTLISTR_LLM_API_KEY")] == "sk-real-123"
    assert "SHORTLISTR_LLM_API_KEY=\n" in env.read_text()  # blanked, no inline comment

    # Re-run must NOT clobber the keychain with a marker/empty value (the F1 bug).
    assert s.migrate_env_to_keyring(str(env)) == []
    assert store[(s.SERVICE, "SHORTLISTR_LLM_API_KEY")] == "sk-real-123"


def test_migrate_heals_poisoned_lines(tmp_path, monkeypatch):
    import secrets_store as s

    store: dict = {}

    class FakeKR:
        def set_password(self, svc, name, val):
            store[(svc, name)] = val

        def get_password(self, svc, name):
            return store.get((svc, name))

        def delete_password(self, svc, name):
            store.pop((svc, name), None)

    monkeypatch.setattr(s, "_keyring", lambda: FakeKR())
    env = tmp_path / ".env"
    env.write_text("SHORTLISTR_LLM_API_KEY=  # moved to OS keychain\nOTHER=keep\n")

    # The marker is not a real secret: heal the line to blank, store nothing.
    assert s.migrate_env_to_keyring(str(env)) == []
    assert "SHORTLISTR_LLM_API_KEY=\n" in env.read_text()
    assert (s.SERVICE, "SHORTLISTR_LLM_API_KEY") not in store


def test_migrate_noop_without_backend(tmp_path):
    import secrets_store as s

    env = tmp_path / ".env"
    env.write_text("SHORTLISTR_LLM_API_KEY=sk-secret\nOTHER=keep\n")
    # Keychain is off under pytest → migration is a safe no-op, file untouched.
    assert s.migrate_env_to_keyring(str(env)) == []
    assert "SHORTLISTR_LLM_API_KEY=sk-secret" in env.read_text()
