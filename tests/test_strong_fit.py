"""strong_fit was structurally incapable of being anything but zero.

Three separate reasons, each of which alone was enough:

1. The synchronous discover endpoint passed `strong_fit=0` as a literal to
   finish_run. Nothing computed it.
2. Even computed, it could not have fired. At scan time a job has no
   description, so the score ceiling is 40 (title) + 10 ("JD not fetched yet")
   + 10 (preferred location) = 60 — the skill-overlap component worth up to 40
   needs a JD. That is why 90 jobs on a real inbox sat at exactly 60, and why
   any threshold above 60 counted nothing. It has to be counted from the
   database, after enrichment has fetched descriptions and re-scored.
3. The path the dashboard actually uses never recorded a run at all. The UI
   calls /jobs/discover?async_run=true, which enqueues; the worker ran the scan
   but called neither start_run nor finish_run, so no scan a user triggered ever
   wrote a runs row.

The bar is its own setting. Reusing MIN_FIT_SCORE would make strong_fit equal to
the number of jobs kept: on a real inbox 40 marks 132 of 210 jobs and 70 marks 5.
"""

from __future__ import annotations

import os
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))


class Rec:
    """A JobRecord-like object: discovery returns these, the filter returns dicts."""

    def __init__(self, url, fit_score=None):
        self.url = url
        self.fit_score = fit_score


# ── the in-memory count ──────────────────────────────────────────────────────

def test_only_jobs_over_the_bar_are_counted(monkeypatch):
    import config as cfg
    from processors.job_filter import count_strong_fit

    monkeypatch.setattr(cfg, "STRONG_FIT_SCORE", 70)
    assert count_strong_fit([Rec("a", 90), Rec("b", 70), Rec("c", 69), Rec("d", 20)]) == 2


def test_dicts_and_objects_both_work(monkeypatch):
    import config as cfg
    from processors.job_filter import count_strong_fit

    monkeypatch.setattr(cfg, "STRONG_FIT_SCORE", 70)
    assert count_strong_fit([{"fit_score": 80}, Rec("b", 80)]) == 2


def test_a_missing_or_junk_score_is_not_strong(monkeypatch):
    import config as cfg
    from processors.job_filter import count_strong_fit

    monkeypatch.setattr(cfg, "STRONG_FIT_SCORE", 70)
    assert count_strong_fit([Rec("a"), {"fit_score": None}, {}, {"fit_score": "high"}]) == 0


def test_nothing_in_nothing_out():
    from processors.job_filter import count_strong_fit

    assert count_strong_fit([]) == 0
    assert count_strong_fit(None) == 0


# ── the bar itself ───────────────────────────────────────────────────────────

def test_strong_is_a_higher_bar_than_keeping():
    """If these were equal, strong_fit would just restate 'kept'."""
    import config as cfg

    assert cfg.STRONG_FIT_SCORE > cfg.MIN_FIT_SCORE


def test_the_bar_clears_the_scan_time_ceiling():
    """A job with no JD tops out at 60: title 40 + no-JD 10 + location 10.

    A bar at or below that would mark almost everything as strong the moment it
    was discovered, before anything had read the description.
    """
    import config as cfg

    assert cfg.STRONG_FIT_SCORE > 60


# ── counting from the database ───────────────────────────────────────────────

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


def _store(conn, url, score):
    from models.job import job_id_from_url

    conn.execute(
        "INSERT INTO jobs (id, url, source, company, title, fit_score) "
        "VALUES (?, ?, 'test', 'Acme', 'SRE', ?)",
        (job_id_from_url(url), url, score),
    )


def test_the_database_score_wins_over_the_scan_time_one(isolated, monkeypatch):
    """The whole point: enrichment raises the score after the scan list is built.

    The in-memory record still carries 60 from scan time; the row has been
    re-scored to 85 since. Counting the record would report zero forever.
    """
    import config as cfg
    from processors.job_filter import count_strong_fit_persisted
    from store import db as store

    monkeypatch.setattr(cfg, "STRONG_FIT_SCORE", 70)
    with store.db() as conn:
        _store(conn, "https://x.test/1", 85)

    assert count_strong_fit_persisted([Rec("https://x.test/1", 60)]) == 1


def test_a_job_still_below_the_bar_is_not_counted(isolated, monkeypatch):
    import config as cfg
    from processors.job_filter import count_strong_fit_persisted
    from store import db as store

    monkeypatch.setattr(cfg, "STRONG_FIT_SCORE", 70)
    with store.db() as conn:
        _store(conn, "https://x.test/1", 60)

    assert count_strong_fit_persisted([Rec("https://x.test/1", 60)]) == 0


def test_a_record_with_no_row_yet_is_not_counted(isolated, monkeypatch):
    """Dry runs score without persisting; nothing to count is zero, not a crash."""
    import config as cfg
    from processors.job_filter import count_strong_fit_persisted

    monkeypatch.setattr(cfg, "STRONG_FIT_SCORE", 70)
    assert count_strong_fit_persisted([Rec("https://x.test/never-stored", 99)]) == 0


def test_records_without_a_url_are_skipped(isolated):
    from processors.job_filter import count_strong_fit_persisted

    assert count_strong_fit_persisted([Rec(None, 99), Rec("", 99)]) == 0


def test_more_records_than_sqlite_takes_parameters(isolated, monkeypatch):
    """SQLite caps host parameters just under 1000; a big scan must not blow up."""
    import config as cfg
    from processors.job_filter import count_strong_fit_persisted
    from store import db as store

    monkeypatch.setattr(cfg, "STRONG_FIT_SCORE", 70)
    urls = [f"https://x.test/{i}" for i in range(1200)]
    with store.db() as conn:
        for i, u in enumerate(urls):
            _store(conn, u, 90 if i % 2 == 0 else 10)

    assert count_strong_fit_persisted([Rec(u) for u in urls]) == 600


def test_duplicate_records_are_counted_once(isolated, monkeypatch):
    """Two sources finding the same posting is one strong fit, not two."""
    import config as cfg
    from processors.job_filter import count_strong_fit_persisted
    from store import db as store

    monkeypatch.setattr(cfg, "STRONG_FIT_SCORE", 70)
    with store.db() as conn:
        _store(conn, "https://x.test/1", 90)

    assert count_strong_fit_persisted([Rec("https://x.test/1"), Rec("https://x.test/1")]) == 1
