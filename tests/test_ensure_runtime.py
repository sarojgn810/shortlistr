"""Tests for automatic Node.js provisioning on first start."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "automation"))

from bootstrap import ensure_runtime as er  # noqa: E402


def test_node_ok_when_present(monkeypatch):
    monkeypatch.setattr(er, "find_node_npm", lambda: ("/usr/bin/node", "/usr/bin/npm", 20))
    monkeypatch.setattr(
        er.subprocess,
        "run",
        lambda *a, **k: type("R", (), {"stdout": "v20.19.4\n", "returncode": 0})(),
    )
    assert er.ensure_node(auto_install=False) is True


def test_ensure_node_fails_cleanly_without_auto_install(monkeypatch):
    monkeypatch.setattr(er, "find_node_npm", lambda: (None, None, None))
    assert er.ensure_node(auto_install=False) is False


def test_ensure_node_tries_pkg_then_portable(monkeypatch):
    calls: list[str] = []

    monkeypatch.setattr(er, "find_node_npm", lambda: (None, None, None))

    def fake_pkg():
        calls.append("pkg")
        return False

    def fake_portable():
        calls.append("portable")
        return True

    monkeypatch.setattr(er, "_try_package_manager", fake_pkg)
    monkeypatch.setattr(er, "_install_portable_node", fake_portable)
    assert er.ensure_node(auto_install=True) is True
    assert calls == ["pkg", "portable"]


def test_dist_slug_known_platforms(monkeypatch):
    monkeypatch.setattr(er.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(er.platform, "machine", lambda: "arm64")
    assert er._dist_slug() == ("darwin-arm64", "tar.gz")

    monkeypatch.setattr(er.platform, "system", lambda: "Linux")
    monkeypatch.setattr(er.platform, "machine", lambda: "x86_64")
    assert er._dist_slug() == ("linux-x64", "tar.gz")

    monkeypatch.setattr(er.platform, "system", lambda: "Windows")
    monkeypatch.setattr(er.platform, "machine", lambda: "AMD64")
    assert er._dist_slug() == ("win-x64", "zip")


def test_prepend_path_puts_dir_first(monkeypatch, tmp_path):
    d = tmp_path / "bin"
    d.mkdir()
    monkeypatch.setenv("PATH", "/usr/bin")
    er._prepend_path(d)
    assert os.environ["PATH"].split(os.pathsep)[0] == str(d)


def test_launcher_check_prereqs_wires_ensure(monkeypatch):
    import launcher

    monkeypatch.setattr("bootstrap.ensure_runtime.ensure_python", lambda: True)
    monkeypatch.setattr("bootstrap.ensure_runtime.ensure_node", lambda auto_install=True: True)
    assert launcher.check_prereqs(auto_install_node=True) is True

    monkeypatch.setattr("bootstrap.ensure_runtime.ensure_node", lambda auto_install=True: False)
    assert launcher.check_prereqs(auto_install_node=True) is False
