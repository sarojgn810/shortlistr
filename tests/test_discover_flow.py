"""Discover queue + progressive persist — the 'scan did nothing' regressions."""

from __future__ import annotations

import os
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))


@pytest.fixture
def isolated_data_dir(monkeypatch):
    tmp = tempfile.mkdtemp()
    import config
    import store.db as db_mod

    monkeypatch.setattr(config, "DATA_DIR", tmp)
    monkeypatch.setattr(db_mod, "DATA_DIR", tmp)
    monkeypatch.setattr(db_mod, "DB_PATH", os.path.join(tmp, "shortlistr.db"))
    return tmp


def _queue_rows():
    from store import db as store

    with store.db() as conn:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT id, task_type, status FROM worker_queue ORDER BY id"
            ).fetchall()
        ]


def test_second_scan_click_reuses_the_queued_task(isolated_data_dir):
    """Two clicks must not stack two full multi-board scrapes."""
    from store import db as store

    store.init_db()
    first = store.enqueue_task("discover", {"dry_run": False})
    second = store.enqueue_task("discover", {"dry_run": False})

    assert first == second
    assert len([r for r in _queue_rows() if r["task_type"] == "discover"]) == 1


def test_claim_marks_running_and_collapses_duplicates(isolated_data_dir):
    from store import db as store
    from workers.discovery_worker import _claim_pending

    store.init_db()
    # Simulate rows written before the dedupe guard existed.
    with store.db() as conn:
        conn.execute("INSERT INTO worker_queue (task_type, payload_json) VALUES ('discover', '{}')")
        conn.execute("INSERT INTO worker_queue (task_type, payload_json) VALUES ('discover', '{}')")

    claimed = _claim_pending()
    assert len(claimed) == 1

    statuses = {r["id"]: r["status"] for r in _queue_rows()}
    assert list(statuses.values()).count("running") == 1
    assert list(statuses.values()).count("cancelled") == 1


def test_progressive_persist_writes_after_each_source(isolated_data_dir, monkeypatch):
    """Jobs must land per source, not only when the slowest source finishes."""
    import config as cfg
    import orchestrator.discovery as disc
    from models.job import JobRecord
    from sources.base import FetchStats
    from store import db as store

    store.init_db()
    monkeypatch.setattr(cfg, "SEARCH_KEYWORDS", ["Site Reliability Engineer", "SRE"])
    monkeypatch.setattr(cfg, "LOCATION_KEYWORDS", ["remote"])
    monkeypatch.setattr(cfg, "LOCATION_PREFERENCE_SET", True)
    monkeypatch.setattr(cfg, "WANTS_REMOTE", True)
    monkeypatch.setattr(cfg, "REMOTE_STRICT", False)
    # Short stub JDs score low — pin the floor so the progressive-write
    # assertion is about persistence order, not fit heuristics.
    monkeypatch.setattr(cfg, "MIN_FIT_SCORE", 0)

    persisted_snapshots: list[int] = []

    class FakeAdapter:
        def __init__(self, name: str, url: str):
            self.name = name
            self._url = url

        def fetch_raw(self, log_totals: bool = False):
            # Each call records how many jobs were already in the DB, proving the
            # previous source was persisted before this one started.
            with store.db() as conn:
                persisted_snapshots.append(
                    int(conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0])
                )
            job = JobRecord(
                url=self._url,
                source=self.name,
                company="Acme",
                title="Site Reliability Engineer",
                location="Remote",
                jd_text="Kubernetes on-call",
            )
            return [job], FetchStats(source=self.name, raw_count=1)

    class FakeRegistry:
        def adapters(self):
            return [
                FakeAdapter("alpha", "https://example.com/jobs/alpha-1"),
                FakeAdapter("beta", "https://example.com/jobs/beta-1"),
            ]

    monkeypatch.setattr(disc, "get_registry", lambda: FakeRegistry())

    passed, rejected, stats = disc.discover_and_filter(persist_progressively=True)

    assert len(passed) + len(rejected) == 2
    # alpha saw an empty DB; beta saw alpha's job already stored.
    assert persisted_snapshots == [0, 1]
    with store.db() as conn:
        assert int(conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]) == 2
    assert stats["discovery_filter"]["passed"] == len(passed)


def test_manual_scan_stamps_last_scan(isolated_data_dir, monkeypatch):
    """A manual scan must move "Last scan" — otherwise the click looks inert."""
    import workers.discovery_worker as worker
    from store import db as store
    from store.settings import get_automation_settings

    store.init_db()
    monkeypatch.setattr(
        "orchestrator.discovery.discover_and_filter",
        lambda **_kw: ([], [], {"alpha": {"raw": 0}, "beta": {"error": "429"}, "discovery_filter": {}}),
    )
    monkeypatch.setattr(
        "scheduler.scan_scheduler.auto_evaluate_pending", lambda **_kw: (0, 0)
    )

    worker._run_discover({})

    settings = get_automation_settings()
    assert settings["last_scan_at"]
    # "discovery_filter" is a summary row, not a source.
    assert settings["last_scan_sources_total"] == 2
    assert settings["last_scan_sources_ok"] == 1


def test_persist_discovered_handles_empty_list(isolated_data_dir):
    from orchestrator.discovery import persist_discovered
    from store import db as store

    store.init_db()
    assert persist_discovered([]) == 0
