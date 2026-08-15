"""Bulk re-evaluation of jobs scored before requirements were recorded.

Backfilling from stored evidence handles every evaluation that has a
requirement list. The rest — 304 of 552 on the corpus this was built against —
carry a number the model guessed and nothing to recompute from, so they need
reading again. That is minutes of LLM calls, not arithmetic, which is why it
runs through the worker queue rather than inside a request.
"""

from __future__ import annotations

import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))


@pytest.fixture
def store(monkeypatch, tmp_path):
    import config

    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    import store.db as db

    monkeypatch.setattr(db, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(db, "DB_PATH", os.path.join(str(tmp_path), "shortlistr.db"))
    db.init_db()
    return db


def add(db, job_id, *, must_haves, status="evaluated"):
    payload = {"schema_version": "v1", "score": 4.5, "legitimacy": "likely",
               "company": "Acme", "role": "SRE", "blocks": {"A": "x"},
               "must_haves": must_haves}
    with db.db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO jobs (id,url,source,company,title,jd_text) VALUES (?,?,?,?,?,?)",
            (job_id, f"https://x.test/{job_id}", "test", "Acme", "SRE", "x" * 400))
        conn.execute("INSERT INTO pipeline (job_id,status) VALUES (?,?)", (job_id, status))
        conn.execute(
            "INSERT INTO eval_results (job_id,schema_version,score,legitimacy,result_json) "
            "VALUES (?,?,?,?,?)", (job_id, "v1", 4.5, "likely", json.dumps(payload)))


def test_finds_only_jobs_without_evidence(store):
    from review.reevaluate import jobs_needing_evidence

    add(store, "has", must_haves=[{"req": "k8s", "met": True, "evidence": "cv"}])
    add(store, "needs", must_haves=[])

    assert jobs_needing_evidence() == ["needs"]


def test_ignores_jobs_already_decided(store):
    from review.reevaluate import jobs_needing_evidence

    add(store, "open", must_haves=[])
    add(store, "approved", must_haves=[], status="approved")
    add(store, "skipped", must_haves=[], status="skipped")

    # Re-reading a job the user already ruled on spends tokens to change nothing.
    assert jobs_needing_evidence() == ["open"]


def test_respects_a_limit(store):
    from review.reevaluate import jobs_needing_evidence

    for i in range(6):
        add(store, f"j{i}", must_haves=[])

    assert len(jobs_needing_evidence(limit=2)) == 2


def test_enqueues_one_task_per_job(store, monkeypatch):
    from review import reevaluate

    add(store, "a", must_haves=[])
    add(store, "b", must_haves=[])

    queued: list[tuple] = []
    monkeypatch.setattr(store, "enqueue_task", lambda t, p: queued.append((t, p)) or len(queued))

    result = reevaluate.enqueue_reevaluation()

    assert result["enqueued"] == 2
    assert {p["job_id"] for _, p in queued} == {"a", "b"}
    # Reuses the existing per-job task type rather than inventing a batch one:
    # a failure then costs a single job, not the whole run.
    assert {t for t, _ in queued} == {"evaluate"}


def test_reports_nothing_to_do(store):
    from review import reevaluate

    add(store, "has", must_haves=[{"req": "k8s", "met": True, "evidence": "cv"}])

    assert reevaluate.enqueue_reevaluation()["enqueued"] == 0


def test_worker_understands_the_task_type():
    from workers import discovery_worker

    # The dispatch loop wraps every branch in _heartbeating(), so a task type it
    # does not recognise raises and the row is failed rather than being reaped
    # mid-run. "evaluate" must stay a known branch.
    source = open(discovery_worker.__file__.replace(".pyc", ".py")).read()
    assert 'task_type == "evaluate"' in source
