"""Recorded HTTP fixtures for ATS resolve — no live network in CI."""

from __future__ import annotations

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))

FIXTURES = os.path.join(ROOT, "tests", "fixtures", "http")


def _load(name: str) -> dict:
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as f:
        return json.load(f)


def test_greenhouse_resolve_from_fixture():
    from scrapers.ats_url_resolver import _fetch_greenhouse

    payload = _load("greenhouse_single_job.json")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = payload

    with patch("scrapers.ats_url_resolver.requests.get", return_value=mock_resp):
        result = _fetch_greenhouse("yugabyte", "7163522", "https://boards.greenhouse.io/yugabyte/jobs/7163522")

    assert result is not None
    assert result["title"] == "Sr DevOps Engineer"
    assert "YugabyteDB" in result["jd_snippet"]
    assert "<div>" not in result["jd_snippet"]


def test_greenhouse_resolve_404_returns_none():
    from scrapers.ats_url_resolver import _fetch_greenhouse

    mock_resp = MagicMock()
    mock_resp.status_code = 404

    with patch("scrapers.ats_url_resolver.requests.get", return_value=mock_resp):
        result = _fetch_greenhouse("missing", "1", "https://boards.greenhouse.io/missing/jobs/1")

    assert result is None


def test_tracker_board_columns(isolated_data_dir):
    from api.tracker_board import fetch_tracker_board, _column_for_row
    from models.job import JobRecord
    from store import db as store

    assert _column_for_row("evaluated", "evaluated") == "review"
    assert _column_for_row("approved", "evaluated") == "approved"
    assert _column_for_row("submitted", "applied") == "submitted"
    assert _column_for_row("approved", "interview") == "active"

    store.init_db()
    job = JobRecord(
        url="https://boards.greenhouse.io/acme/jobs/1",
        source="import",
        company="Acme",
        title="SRE",
    )
    store.upsert_job(job)
    store.add_to_pipeline(job.job_id)
    from store.status import mark_evaluated, mark_approved

    mark_evaluated(job.job_id, company="Acme", role="SRE", score=4.2)
    mark_approved(job.job_id)

    with store.db() as conn:
        board = fetch_tracker_board(conn)
    assert board["counts"]["approved"] >= 1
    card = next(c for c in board["columns"]["approved"] if c["job_id"] == job.job_id)
    assert card.get("score") == 4.2
    # Unevaluated discovery fit is exposed when present; this row may be 0.
    assert "fit_score" in card


def test_tracker_board_review_hides_off_target(isolated_data_dir, monkeypatch):
    """Review is the same judgment queue as Discover, so it takes the same gate."""
    import config as cfg
    from api.tracker_board import fetch_tracker_board
    from models.job import JobRecord
    from store import db as store
    from store.status import mark_evaluated, mark_approved

    monkeypatch.setattr(cfg, "MIN_FIT_SCORE", 40)

    store.init_db()

    def add(url, title, *, fit, relevance):
        job = JobRecord(url=url, source="import", company="Acme", title=title)
        job.fit_score = fit
        job.metadata["discovery_relevance"] = relevance
        store.upsert_job(job)
        store.add_to_pipeline(job.job_id)
        return job.job_id

    on_target = add("https://x.test/1", "SRE", fit=60, relevance="relevant")
    off_target = add("https://x.test/2", "Account Executive", fit=0, relevance="off_target")
    low_fit = add("https://x.test/3", "Data Analyst", fit=10, relevance="relevant")
    # Approved before a retarget: the user's decision outranks current targeting.
    decided = add("https://x.test/4", "Management Accountant", fit=0, relevance="off_target")
    mark_evaluated(decided, company="Acme", role="Management Accountant", score=4.2)
    mark_approved(decided)

    with store.db() as conn:
        board = fetch_tracker_board(conn)
        every = fetch_tracker_board(conn, relevance="all")

    review = {r["job_id"] for r in board["columns"]["review"]}
    assert review == {on_target}
    assert off_target not in review
    assert low_fit not in review
    assert decided in {r["job_id"] for r in board["columns"]["approved"]}

    assert {r["job_id"] for r in every["columns"]["review"]} == {on_target, off_target, low_fit}


def test_pipeline_counts_targeted_vs_raw(isolated_data_dir, monkeypatch):
    """Headline counts must match the filtered list; raw counts stay available."""
    import config as cfg
    from models.job import JobRecord
    from store import db as store
    from store.status import pipeline_status_counts

    monkeypatch.setattr(cfg, "MIN_FIT_SCORE", 40)
    store.init_db()

    for url, fit, relevance in [
        ("https://x.test/a", 60, "relevant"),
        ("https://x.test/b", 0, "off_target"),
        ("https://x.test/c", 5, "relevant"),
    ]:
        job = JobRecord(url=url, source="import", company="Acme", title="Role")
        job.fit_score = fit
        job.metadata["discovery_relevance"] = relevance
        store.upsert_job(job)
        store.add_to_pipeline(job.job_id)

    assert pipeline_status_counts()["pending"] == 3
    assert pipeline_status_counts(targeted=True)["pending"] == 1


def test_min_fit_threshold_respects_zero(monkeypatch):
    """0 means 'show everything' — a truthiness check would re-impose the floor."""
    import config as cfg
    from store.queries import DEFAULT_MIN_FIT, min_fit_threshold

    monkeypatch.setattr(cfg, "MIN_FIT_SCORE", 0)
    assert min_fit_threshold() == 0

    monkeypatch.setattr(cfg, "MIN_FIT_SCORE", 55)
    assert min_fit_threshold() == 55

    monkeypatch.setattr(cfg, "MIN_FIT_SCORE", None)
    assert min_fit_threshold() == DEFAULT_MIN_FIT


@pytest.fixture
def isolated_data_dir(monkeypatch):
    import tempfile

    tmp = tempfile.mkdtemp()
    import config
    import store.db as db_mod

    monkeypatch.setattr(config, "DATA_DIR", tmp)
    monkeypatch.setattr(db_mod, "DATA_DIR", tmp)
    monkeypatch.setattr(db_mod, "DB_PATH", os.path.join(tmp, "shortlistr.db"))
    return tmp
