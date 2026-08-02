"""A job with a description must not stay scored as if it had none.

The enrichment pass re-scores what it fetches, but it only selects rows whose
jd_text is missing or short. A job whose description arrived by another path —
the URL resolver, the eval enricher, a source that ships it inline — kept its
title-only score and the reason "JD not fetched yet" permanently.

On a real inbox that was 94 of 158 jobs, all pinned at a flat 50 or 60, so
Discover could not rank them and the UI claimed the description had not been
fetched while displaying it.
"""

from __future__ import annotations

import os
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))


@pytest.fixture
def isolated(monkeypatch):
    tmp = tempfile.mkdtemp()
    import config
    import store.db as db_mod

    monkeypatch.setattr(config, "DATA_DIR", tmp)
    monkeypatch.setattr(db_mod, "DATA_DIR", tmp)
    monkeypatch.setattr(db_mod, "DB_PATH", os.path.join(tmp, "shortlistr.db"))
    monkeypatch.setattr(db_mod, "LEGACY_DB_PATH", os.path.join(tmp, "autojob.db"))
    db_mod.init_db()
    return tmp


def _job(conn, jid, *, jd, reason, score=50):
    conn.execute(
        "INSERT INTO jobs (id, url, source, company, title, location, jd_text, "
        "fit_score, fit_reason) VALUES (?, ?, 'workday', 'Acme', "
        "'Site Reliability Engineer', 'Bengaluru', ?, ?, ?)",
        (jid, f"https://x.test/{jid}", jd, score, reason),
    )


def test_a_job_with_a_jd_is_rescored(isolated, monkeypatch):
    from processors.enrich_jd import rescore_fetched_jobs
    from store import db as store

    with store.db() as conn:
        _job(conn, "a", jd="kubernetes on-call terraform " * 40,
             reason="title match; JD not fetched yet")

    monkeypatch.setattr("processors.job_filter.score_job",
                        lambda job: {"fit_score": 85, "fit_reason": "strong JD overlap"})
    res = rescore_fetched_jobs()
    assert res == {"candidates": 1, "rescored": 1}

    with store.db() as conn:
        row = conn.execute("SELECT fit_score, fit_reason FROM jobs WHERE id='a'").fetchone()
    assert row["fit_score"] == 85
    assert "not fetched" not in row["fit_reason"]


def test_a_job_without_a_jd_is_left_alone(isolated, monkeypatch):
    """Those belong to the enrichment pass — re-scoring them changes nothing."""
    from processors.enrich_jd import rescore_fetched_jobs
    from store import db as store

    with store.db() as conn:
        _job(conn, "a", jd="", reason="title match; JD not fetched yet")

    called = []
    monkeypatch.setattr("processors.job_filter.score_job",
                        lambda job: called.append(1) or {"fit_score": 9, "fit_reason": "x"})
    assert rescore_fetched_jobs()["rescored"] == 0
    assert not called


def test_an_already_scored_job_is_not_touched(isolated, monkeypatch):
    """Only rows still claiming the JD was never fetched are candidates."""
    from processors.enrich_jd import rescore_fetched_jobs
    from store import db as store

    with store.db() as conn:
        _job(conn, "a", jd="kubernetes " * 100, reason="strong JD overlap", score=80)

    monkeypatch.setattr("processors.job_filter.score_job",
                        lambda job: {"fit_score": 10, "fit_reason": "should not run"})
    assert rescore_fetched_jobs()["candidates"] == 0

    with store.db() as conn:
        row = conn.execute("SELECT fit_score FROM jobs WHERE id='a'").fetchone()
    assert row["fit_score"] == 80


def test_an_archived_job_is_skipped(isolated, monkeypatch):
    from processors.enrich_jd import rescore_fetched_jobs
    from store import db as store

    with store.db() as conn:
        _job(conn, "a", jd="kubernetes " * 100, reason="title match; JD not fetched yet")
        conn.execute("UPDATE jobs SET archived_at = datetime('now') WHERE id='a'")

    monkeypatch.setattr("processors.job_filter.score_job",
                        lambda job: {"fit_score": 85, "fit_reason": "x"})
    assert rescore_fetched_jobs()["candidates"] == 0


def test_a_scorer_returning_nothing_leaves_the_row_unchanged(isolated, monkeypatch):
    """Never overwrite a reason with an empty one — that loses information."""
    from processors.enrich_jd import rescore_fetched_jobs
    from store import db as store

    with store.db() as conn:
        _job(conn, "a", jd="kubernetes " * 100, reason="title match; JD not fetched yet")

    monkeypatch.setattr("processors.job_filter.score_job",
                        lambda job: {"fit_score": 0, "fit_reason": ""})
    assert rescore_fetched_jobs()["rescored"] == 0

    with store.db() as conn:
        row = conn.execute("SELECT fit_score, fit_reason FROM jobs WHERE id='a'").fetchone()
    assert row["fit_score"] == 50 and "not fetched" in row["fit_reason"]


def test_a_zero_score_keeps_the_previous_number(isolated, monkeypatch):
    """A scorer that produces a reason but no number must not zero the fit."""
    from processors.enrich_jd import rescore_fetched_jobs
    from store import db as store

    with store.db() as conn:
        _job(conn, "a", jd="kubernetes " * 100,
             reason="title match; JD not fetched yet", score=60)

    monkeypatch.setattr("processors.job_filter.score_job",
                        lambda job: {"fit_score": 0, "fit_reason": "weak overlap"})
    rescore_fetched_jobs()

    with store.db() as conn:
        row = conn.execute("SELECT fit_score, fit_reason FROM jobs WHERE id='a'").fetchone()
    assert row["fit_score"] == 60
    assert row["fit_reason"] == "weak overlap"
