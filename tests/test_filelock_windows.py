"""The database must work on a machine without fcntl.

`fcntl` is Unix-only and was imported unconditionally inside `init_db()` and at
the top of the ingest module. On a Windows clone the app booted, served /health,
and then returned 500 for /setup/status, /pipeline/stats, /cv/status and
/cv/upload — every route that touches the database — with:

    ModuleNotFoundError: No module named 'fcntl'

Onboarding could not get past uploading a résumé, and the scheduler logged
"Scheduler tick: No module named 'fcntl'" on every tick.

The lock only stops two processes migrating at the same instant; SQLite
serialises writers by itself. So a platform with no locking primitive is told it
holds the lock and carries on. Refusing to work is much worse than a rare retry.
"""

from __future__ import annotations

import os
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))

from store import filelock


class FakeMsvcrt:
    """The three calls Windows offers, and whether the byte is currently held."""

    LK_LOCK, LK_NBLCK, LK_UNLCK = 1, 2, 0

    def __init__(self, held: bool = False):
        self.modes: list[int] = []
        self.held = held

    def locking(self, fd, mode, nbytes):
        self.modes.append(mode)
        if mode in (self.LK_LOCK, self.LK_NBLCK):
            if self.held:
                raise OSError("already locked")
            self.held = True
        else:
            self.held = False


@pytest.fixture
def handle(tmp_path):
    with open(tmp_path / "lock", "w") as fh:
        yield fh


@pytest.fixture(autouse=True)
def restore():
    """These tests rewrite module globals; put them back."""
    real_fcntl, real_msvcrt = filelock.fcntl, filelock.msvcrt
    yield
    filelock.fcntl, filelock.msvcrt = real_fcntl, real_msvcrt


# ── no locking primitive at all ──────────────────────────────────────────────

def test_without_any_primitive_the_caller_still_proceeds(handle):
    """True means "go ahead". Returning False here would stop the app booting."""
    filelock.fcntl = None
    filelock.msvcrt = None
    assert filelock.acquire(handle) is True


def test_releasing_without_a_primitive_is_silent(handle):
    filelock.fcntl = None
    filelock.msvcrt = None
    filelock.release(handle)  # must not raise


# ── the Windows path ─────────────────────────────────────────────────────────

def test_windows_takes_and_drops_the_lock(handle):
    filelock.fcntl = None
    filelock.msvcrt = fake = FakeMsvcrt()

    assert filelock.acquire(handle) is True
    assert fake.modes == [FakeMsvcrt.LK_LOCK]

    filelock.release(handle)
    assert fake.modes == [FakeMsvcrt.LK_LOCK, FakeMsvcrt.LK_UNLCK]
    assert fake.held is False


def test_windows_non_blocking_reports_a_held_lock(handle):
    """This is what makes an overrunning ingest tick skip instead of stack."""
    filelock.fcntl = None
    filelock.msvcrt = FakeMsvcrt(held=True)

    assert filelock.acquire(handle, blocking=False) is False


def test_windows_blocking_gives_up_rather_than_hanging(handle):
    """LK_LOCK has already retried for ~10s. Waiting forever would hang boot."""
    filelock.fcntl = None
    filelock.msvcrt = FakeMsvcrt(held=True)

    assert filelock.acquire(handle, blocking=True) is True


# ── the actual failure the user hit ──────────────────────────────────────────

def test_the_database_works_with_no_locking_primitive(monkeypatch):
    """init_db, a query and audit() — the three routes that 500'd on Windows."""
    filelock.fcntl = None
    filelock.msvcrt = None

    tmp = tempfile.mkdtemp()
    import config
    import store.db as db_mod

    monkeypatch.setattr(config, "DATA_DIR", tmp)
    monkeypatch.setattr(db_mod, "DATA_DIR", tmp)
    monkeypatch.setattr(db_mod, "DB_PATH", os.path.join(tmp, "shortlistr.db"))
    monkeypatch.setattr(db_mod, "LEGACY_DB_PATH", os.path.join(tmp, "autojob.db"))
    db_mod._initialized_dbs.clear()

    db_mod.init_db()
    with db_mod.db() as conn:
        conn.execute("SELECT COUNT(*) FROM jobs").fetchone()
    db_mod.audit("cv_uploaded", "cv", "x", {"bytes": 1})


def test_ingest_does_not_import_fcntl_at_module_scope():
    """A module-level import breaks the scheduler tick before any guard runs."""
    src = open(os.path.join(ROOT, "automation", "jobs", "ingest.py"), encoding="utf-8").read()
    assert "import fcntl" not in src


def test_only_filelock_touches_fcntl():
    """Any new bare import puts Windows back where it started."""
    offenders = []
    for base, _dirs, files in os.walk(os.path.join(ROOT, "automation")):
        for name in files:
            if not name.endswith(".py") or name == "filelock.py":
                continue
            path = os.path.join(base, name)
            if "import fcntl" in open(path, encoding="utf-8", errors="ignore").read():
                offenders.append(os.path.relpath(path, ROOT))
    assert offenders == [], f"import fcntl outside filelock.py: {offenders}"
