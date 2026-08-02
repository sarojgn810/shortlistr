"""SQLite connection settings that keep Discover readable during scans."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "automation"))


def test_connect_enables_wal_and_busy_timeout(tmp_path, monkeypatch):
    import config
    import store.db as db_mod

    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr(config, "DATA_DIR", str(data), raising=False)
    monkeypatch.setattr(db_mod, "DATA_DIR", str(data), raising=False)
    monkeypatch.setattr(db_mod, "DB_PATH", str(data / "shortlistr.db"), raising=False)
    db_mod._initialized_dbs.clear()

    db_mod.init_db()
    conn = db_mod._connect()
    try:
        busy = conn.execute("PRAGMA busy_timeout").fetchone()[0]
        assert int(busy) >= 30000
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert str(mode).lower() == "wal"
    finally:
        conn.close()

    # Second init_db must be a no-op (cached) so scanners don't re-migrate under lock.
    db_mod.init_db()
    assert os.path.abspath(str(data / "shortlistr.db")) in db_mod._initialized_dbs
    assert os.path.isfile(str(data / "shortlistr.db") + ".migrate.lock")
