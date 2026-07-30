"""A dead worker must not wedge the queue forever.

`_claim_pending` marks a row 'running' and only the worker that claimed it ever
moves it off that status. So an API restart (or a kill) mid-scan stranded the
row — and because `_claim_pending` cancels every *new* discover while one is
'running', scanning stopped working permanently. The Scan button, which believes
`GET /jobs/discover/status`, span for a day.
"""

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


def _insert_running(conn, *, minutes_ago: int, task_type: str = "discover") -> int:
    cur = conn.execute(
        """
        INSERT INTO worker_queue (task_type, payload_json, status, created_at, started_at)
        VALUES (?, '{}', 'running', datetime('now', ?), datetime('now', ?))
        """,
        (task_type, f"-{minutes_ago} minutes", f"-{minutes_ago} minutes"),
    )
    return int(cur.lastrowid)


def _statuses(conn) -> dict[str, int]:
    return {
        str(r["status"]): int(r["c"])
        for r in conn.execute(
            "SELECT status, COUNT(*) AS c FROM worker_queue GROUP BY status"
        ).fetchall()
    }


def test_worker_queue_has_started_at(isolated_data_dir):
    """The reaper needs to know when a task was claimed, not when it was queued."""
    from store import db as store

    store.init_db()
    with store.db() as conn:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(worker_queue)")}
    assert "started_at" in cols


def test_a_task_stuck_running_past_the_timeout_is_failed(isolated_data_dir):
    from store import db as store
    from store.db import STALE_TASK_MINUTES, reap_stale_tasks

    store.init_db()
    with store.db() as conn:
        _insert_running(conn, minutes_ago=STALE_TASK_MINUTES + 5)
        assert reap_stale_tasks(conn) == 1
        assert _statuses(conn) == {"failed": 1}


def test_a_task_still_within_the_timeout_is_left_alone(isolated_data_dir):
    """A real multi-board scan takes minutes — reaping it mid-run would restart it."""
    from store import db as store
    from store.db import reap_stale_tasks

    store.init_db()
    with store.db() as conn:
        _insert_running(conn, minutes_ago=1)
        assert reap_stale_tasks(conn) == 0
        assert _statuses(conn) == {"running": 1}


def test_a_row_claimed_before_started_at_existed_still_gets_reaped(isolated_data_dir):
    """Rows written by the old code have started_at NULL; fall back to created_at."""
    from store import db as store
    from store.db import STALE_TASK_MINUTES, reap_stale_tasks

    store.init_db()
    with store.db() as conn:
        conn.execute(
            """
            INSERT INTO worker_queue (task_type, payload_json, status, created_at)
            VALUES ('discover', '{}', 'running', datetime('now', ?))
            """,
            (f"-{STALE_TASK_MINUTES + 60} minutes",),
        )
        assert reap_stale_tasks(conn) == 1
        assert _statuses(conn) == {"failed": 1}


def test_enqueue_is_not_answered_by_a_dead_workers_row(isolated_data_dir):
    """The click that never happened.

    `enqueue_task` dedupes discovers by returning any existing pending/running
    row's id. A stranded 'running' row matched forever, so the API kept replying
    "already queued" and no new scan was ever written.
    """
    from store import db as store
    from store.db import STALE_TASK_MINUTES

    store.init_db()
    with store.db() as conn:
        dead_id = _insert_running(conn, minutes_ago=STALE_TASK_MINUTES + 5)

    new_id = store.enqueue_task("discover", {"dry_run": False})
    assert new_id != dead_id, "the Scan click was answered with the dead row"

    with store.db() as conn:
        assert _statuses(conn) == {"failed": 1, "pending": 1}


def test_enqueue_still_dedupes_a_genuinely_running_scan(isolated_data_dir):
    """Reaping must not undo the "one discover at a time" rule."""
    from store import db as store

    store.init_db()
    with store.db() as conn:
        live_id = _insert_running(conn, minutes_ago=1)

    assert store.enqueue_task("discover", {"dry_run": False}) == live_id


def test_scanning_recovers_after_a_worker_dies(isolated_data_dir):
    """The actual user-visible bug: Scan never works again.

    A stranded 'running' discover made `_claim_pending` cancel each new one, so
    every subsequent click was silently discarded.
    """
    from store import db as store
    from store.db import STALE_TASK_MINUTES
    from workers.discovery_worker import _claim_pending

    store.init_db()
    with store.db() as conn:
        _insert_running(conn, minutes_ago=STALE_TASK_MINUTES + 5)

    store.enqueue_task("discover", {"dry_run": False})
    claimed = _claim_pending()

    assert [t["task_type"] for t in claimed] == ["discover"], (
        "the new scan was cancelled by the dead worker's row"
    )
    with store.db() as conn:
        counts = _statuses(conn)
    assert counts.get("failed") == 1     # the stranded one
    assert counts.get("running") == 1    # the new one, now genuinely in flight


def test_claiming_records_when_the_task_started(isolated_data_dir):
    from store import db as store
    from workers.discovery_worker import _claim_pending

    store.init_db()
    store.enqueue_task("discover", {"dry_run": False})
    _claim_pending()
    with store.db() as conn:
        row = conn.execute(
            "SELECT status, started_at FROM worker_queue ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert row["status"] == "running"
    assert row["started_at"], "started_at must be set at claim time"


def test_discover_status_endpoint_self_heals(isolated_data_dir):
    """Opening Discover must clear a stale spinner even with no worker alive."""
    pytest.importorskip("fastapi")
    from api.main import create_app
    from fastapi.testclient import TestClient
    from store import db as store
    from store.db import STALE_TASK_MINUTES

    store.init_db()
    with store.db() as conn:
        _insert_running(conn, minutes_ago=STALE_TASK_MINUTES + 5)

    client = TestClient(create_app())
    body = client.get("/jobs/discover/status").json()
    assert body["running"] is False
    assert body["queue"].get("running", 0) == 0
