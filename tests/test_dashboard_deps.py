"""Dashboard packages install when they change, not only when they are missing.

Python dependencies reinstall on every `start`, so pulling a commit that adds
one picks it up. Dashboard dependencies did not: the install ran only when
node_modules was absent, so pulling a commit that added a package started the
app against a tree without it. That is the same failure as a
ModuleNotFoundError on first boot, only harder to read — the app comes up and
breaks later, somewhere else.

Hashing the lockfile rather than always shelling out to npm keeps an ordinary
start fast. npm install is a no-op on a current tree, but not a free one.

The stamp lives inside node_modules deliberately: deleting that directory has to
mean "reinstall", and a stamp kept outside would survive it and lie.
"""

from __future__ import annotations

import json
import os
import shutil
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))


@pytest.fixture
def dashboard(monkeypatch, tmp_path):
    """A fake dashboard dir with a lockfile, and npm replaced by a counter."""
    import launcher

    monkeypatch.setattr(launcher, "DASHBOARD", str(tmp_path))
    monkeypatch.setattr(launcher, "_log", lambda *a, **k: None)
    (tmp_path / "package-lock.json").write_text(json.dumps({"deps": ["a"]}))

    runs: list[list[str]] = []

    def fake_run(argv, **kwargs):
        runs.append(argv)
        # A real npm install creates the tree; the stamp write depends on it.
        # Path.mkdir, not os.makedirs — one test patches the latter to prove a
        # failing stamp write does not sink the launch, and patching it globally
        # would break this stand-in too.
        (tmp_path / "node_modules").mkdir(exist_ok=True)
        return type("R", (), {"returncode": 0})()

    monkeypatch.setattr(launcher.subprocess, "run", fake_run)

    def set_lock(payload):
        (tmp_path / "package-lock.json").write_text(json.dumps(payload))

    return launcher, runs, tmp_path, set_lock


def test_a_fresh_clone_installs(dashboard):
    launcher, runs, _, _ = dashboard
    launcher._install_dashboard_deps()
    assert len(runs) == 1


def test_an_unchanged_tree_does_not_reinstall(dashboard):
    """The reason for hashing rather than always running npm."""
    launcher, runs, _, _ = dashboard
    launcher._install_dashboard_deps()
    launcher._install_dashboard_deps()
    launcher._install_dashboard_deps()
    assert len(runs) == 1


def test_a_changed_lockfile_reinstalls(dashboard):
    """The bug: pulling a commit that adds a dashboard package installed nothing."""
    launcher, runs, _, set_lock = dashboard
    launcher._install_dashboard_deps()

    set_lock({"deps": ["a", "b"]})
    launcher._install_dashboard_deps()

    assert len(runs) == 2


def test_it_settles_again_after_that_install(dashboard):
    launcher, runs, _, set_lock = dashboard
    launcher._install_dashboard_deps()
    set_lock({"deps": ["a", "b"]})
    launcher._install_dashboard_deps()
    launcher._install_dashboard_deps()
    assert len(runs) == 2


def test_deleting_node_modules_reinstalls(dashboard):
    """The stamp must not outlive the packages it vouches for."""
    launcher, runs, tmp_path, _ = dashboard
    launcher._install_dashboard_deps()
    shutil.rmtree(tmp_path / "node_modules")

    launcher._install_dashboard_deps()
    assert len(runs) == 2


def test_package_json_is_used_when_there_is_no_lockfile(dashboard):
    launcher, runs, tmp_path, _ = dashboard
    (tmp_path / "package-lock.json").unlink()
    (tmp_path / "package.json").write_text(json.dumps({"deps": ["a"]}))

    launcher._install_dashboard_deps()
    launcher._install_dashboard_deps()
    assert len(runs) == 1, "package.json should be hashed when no lockfile exists"

    (tmp_path / "package.json").write_text(json.dumps({"deps": ["a", "b"]}))
    launcher._install_dashboard_deps()
    assert len(runs) == 2


def test_with_no_manifest_at_all_it_still_installs(dashboard):
    """Nothing to hash is not a reason to skip: install and do not stamp."""
    launcher, runs, tmp_path, _ = dashboard
    (tmp_path / "package-lock.json").unlink()

    launcher._install_dashboard_deps()
    launcher._install_dashboard_deps()
    assert len(runs) == 2, "without a manifest every start must install"


def test_an_unwritable_stamp_does_not_fail_the_start(dashboard, monkeypatch):
    """Losing the stamp costs one extra npm install, not a broken launch."""
    launcher, runs, _, _ = dashboard

    def no_write(*a, **k):
        raise OSError("read-only file system")

    monkeypatch.setattr(launcher.os, "makedirs", no_write)  # stamp write only
    launcher._install_dashboard_deps()
    assert len(runs) == 1


def test_npm_failure_still_stops_the_launcher(dashboard, monkeypatch):
    """check=True is deliberate — starting on a broken tree helps nobody."""
    import subprocess as sp

    launcher, _, _, _ = dashboard

    def boom(argv, **kwargs):
        raise sp.CalledProcessError(1, argv)

    monkeypatch.setattr(launcher.subprocess, "run", boom)
    with pytest.raises(sp.CalledProcessError):
        launcher._install_dashboard_deps()
