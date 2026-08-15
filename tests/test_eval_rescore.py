"""Rescoring stored evaluations from the evidence already on disk.

Every evaluation keeps the requirement list it was judged against, so a scoring
change does not mean re-running the model over hundreds of postings — it means
recomputing arithmetic. On the corpus this was built against that is 248
evaluations rescored instantly, against 304 that predate the list and genuinely
need re-evaluating.
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
    """An isolated database — this writes, so it must not touch real data."""
    import config

    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    import store.db as db

    monkeypatch.setattr(db, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(db, "DB_PATH", os.path.join(str(tmp_path), "shortlistr.db"))
    db.init_db()
    return db


def _add_eval(db, job_id: str, score: float, must_haves, *, company="Acme", role="SRE"):
    # eval_results.job_id references jobs(id) with foreign keys on, so the job
    # row has to exist first.
    with db.db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO jobs (id, url, source, company, title) VALUES (?,?,?,?,?)",
            (job_id, f"https://example.test/{job_id}", "test", company, role),
        )
    payload = {
        "schema_version": "v1",
        "score": score,
        "legitimacy": "likely",
        "company": company,
        "role": role,
        "blocks": {"A": "fit"},
        "must_haves": must_haves,
    }
    with db.db() as conn:
        conn.execute(
            "INSERT INTO eval_results (job_id, schema_version, score, legitimacy, result_json) "
            "VALUES (?,?,?,?,?)",
            (job_id, "v1", score, "likely", json.dumps(payload)),
        )
        conn.execute(
            "INSERT INTO applications (job_id, company, role, score, status) VALUES (?,?,?,?,?)",
            (job_id, company, role, score, "evaluated"),
        )


def met(n):
    return [{"req": f"req {i}", "met": True, "evidence": "cv line"} for i in range(n)]


def unmet(n):
    return [{"req": f"gap {i}", "met": False, "evidence": ""} for i in range(n)]


def test_rescores_from_stored_evidence(store):
    from eval.rescore import rescore_all

    _add_eval(store, "job-deep", 4.5, met(11))
    _add_eval(store, "job-thin", 4.5, met(1))

    report = rescore_all()

    assert report["rescored"] == 2
    with store.db() as conn:
        rows = dict(conn.execute("SELECT job_id, score FROM eval_results").fetchall())
    # Both were 4.5. Eleven proven requirements must now outrank one.
    assert rows["job-deep"] > rows["job-thin"]


def test_updates_the_score_the_ui_reads(store):
    from eval.rescore import rescore_all

    _add_eval(store, "job-1", 4.5, met(2) + unmet(4))
    rescore_all()

    with store.db() as conn:
        app_score = conn.execute("SELECT score FROM applications WHERE job_id='job-1'").fetchone()[0]
        eval_score = conn.execute("SELECT score FROM eval_results WHERE job_id='job-1'").fetchone()[0]

    # The pipeline reads applications.score; leaving it stale would show the old
    # ranking everywhere the user actually looks.
    assert app_score == eval_score
    assert app_score < 4.5


def test_leaves_evaluations_without_evidence_alone(store):
    from eval.rescore import rescore_all

    _add_eval(store, "job-old", 4.5, [])

    report = rescore_all()

    assert report["skipped"] == 1
    assert report["rescored"] == 0
    with store.db() as conn:
        score = conn.execute("SELECT score FROM eval_results WHERE job_id='job-old'").fetchone()[0]
    # No requirement list means nothing to recompute from. Overwriting it with a
    # guess would be worse than leaving the old number and re-evaluating later.
    assert score == 4.5


def test_records_what_it_did_in_the_payload(store):
    from eval.rescore import rescore_all

    _add_eval(store, "job-1", 4.5, met(3) + unmet(1))
    rescore_all()

    with store.db() as conn:
        raw = conn.execute("SELECT result_json FROM eval_results WHERE job_id='job-1'").fetchone()[0]
    payload = json.loads(raw)

    assert payload["score_source"] == "evidence"
    # Keep the number the model produced, so the two can be compared later
    # rather than the old ranking being silently erased.
    assert payload["model_score"] == 4.5


def test_is_idempotent(store):
    from eval.rescore import rescore_all

    _add_eval(store, "job-1", 4.5, met(5))
    first = rescore_all()
    with store.db() as conn:
        after_first = conn.execute("SELECT score FROM eval_results WHERE job_id='job-1'").fetchone()[0]

    second = rescore_all()
    with store.db() as conn:
        after_second = conn.execute("SELECT score FROM eval_results WHERE job_id='job-1'").fetchone()[0]

    assert after_first == after_second
    assert first["rescored"] == second["rescored"] == 1


def test_dry_run_changes_nothing(store):
    from eval.rescore import rescore_all

    _add_eval(store, "job-1", 4.5, met(1))

    report = rescore_all(dry_run=True)

    assert report["rescored"] == 1
    with store.db() as conn:
        score = conn.execute("SELECT score FROM eval_results WHERE job_id='job-1'").fetchone()[0]
    assert score == 4.5, "dry run must not write"


def test_reports_the_shape_of_the_change(store):
    from eval.rescore import rescore_all

    for i in range(5):
        _add_eval(store, f"job-{i}", 4.5, met(6))
    _add_eval(store, "job-thin", 4.5, met(1))

    report = rescore_all(dry_run=True)

    # The point of the change is that the top band stops being everything, so
    # the report has to say what it became.
    assert report["top_band_before"] == 6
    assert report["top_band_after"] < 6
