"""Uninstall helper — safe defaults, no accidental data wipe."""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))


def test_uninstall_keeps_data_by_default(tmp_path, monkeypatch):
    import bootstrap.uninstall as u
    import config

    monkeypatch.setattr(u, "SHORTLISTR_ROOT", str(tmp_path))
    monkeypatch.setattr(config, "SHORTLISTR_ROOT", str(tmp_path))
    monkeypatch.setattr(u, "DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(u, "OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setattr(u, "PROFILE_PATH", str(tmp_path / "config" / "profile.yml"))
    monkeypatch.setattr(u, "_stop_local_servers", lambda: ["stopped"])
    monkeypatch.setattr(u, "_remove_crons", lambda: ["crons"])
    monkeypatch.setattr(u, "_clear_keychain", lambda: ["keychain"])

    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "shortlistr.db").write_text("x", encoding="utf-8")
    (tmp_path / "cv.md").write_text("# me", encoding="utf-8")
    (tmp_path / "dashboard" / "node_modules").mkdir(parents=True)
    (tmp_path / "dashboard" / "node_modules" / "x").write_text("1", encoding="utf-8")

    actions = u.uninstall_local(purge_data=False, purge_build=True, stop_servers=True)
    assert any("stopped" in a for a in actions)
    assert (tmp_path / "cv.md").is_file()
    assert (tmp_path / "data" / "shortlistr.db").is_file()
    assert not (tmp_path / "dashboard" / "node_modules").exists()

    actions2 = u.uninstall_local(purge_data=True, purge_build=False, stop_servers=False)
    assert not (tmp_path / "cv.md").exists()
    assert "Delete the project folder" in u.remaining_steps(purged_data=True)
