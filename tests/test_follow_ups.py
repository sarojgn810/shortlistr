"""Applications the mailbox says are waiting on you.

"Questionnaire still pending from Virtana" means a live application exists and
needs action. The tracker board is job-centric — pipeline JOIN jobs LEFT JOIN
applications — so when the user applied outside this tool there is no job row,
no application row, and nowhere to show it. It was simply lost.
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


def test_the_table_exists_after_migration(isolated):
    from store import db as store

    with store.db() as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='follow_ups'"
        ).fetchone()
    assert row is not None


def test_a_pending_questionnaire_becomes_a_follow_up(isolated):
    from store import follow_ups

    fid = follow_ups.record_follow_up(
        kind="application_update", company="Virtana",
        subject="Questionnaire still pending from Virtana",
    )
    assert fid
    open_rows = follow_ups.list_follow_ups()
    assert len(open_rows) == 1
    assert open_rows[0]["company"] == "Virtana"
    assert open_rows[0]["resolved_at"] is None


def test_the_same_reminder_three_times_is_still_one_follow_up(isolated):
    """Cutshort sends these repeatedly; three rows is nagging, not tracking."""
    from store import follow_ups

    first = follow_ups.record_follow_up(
        kind="application_update", company="Virtana", subject="Questionnaire pending")
    again = follow_ups.record_follow_up(
        kind="application_update", company="Virtana",
        subject="Trying one last time - questionnaire pending")
    assert first and again is None
    rows = follow_ups.list_follow_ups()
    assert len(rows) == 1
    # The row reflects the most recent thing said.
    assert "one last time" in rows[0]["subject"]


def test_different_companies_are_separate_follow_ups(isolated):
    from store import follow_ups

    for co in ("Virtana", "FAiHr", "Fx31labs"):
        follow_ups.record_follow_up(kind="application_update", company=co)
    assert len(follow_ups.list_follow_ups()) == 3


def test_a_follow_up_with_no_company_is_not_recorded(isolated):
    """Without a company there is nothing the user can act on."""
    from store import follow_ups

    assert follow_ups.record_follow_up(kind="application_update", company="  ") is None
    assert follow_ups.list_follow_ups() == []


def test_resolving_hides_it_and_frees_the_company_again(isolated):
    from store import follow_ups

    fid = follow_ups.record_follow_up(kind="application_update", company="Virtana")
    follow_ups.resolve_follow_up(fid)
    assert follow_ups.list_follow_ups() == []
    assert follow_ups.open_count() == 0
    assert len(follow_ups.list_follow_ups(include_resolved=True)) == 1
    # A later reminder for the same company can open a fresh one.
    assert follow_ups.record_follow_up(kind="application_update", company="Virtana")
    assert follow_ups.open_count() == 1


def test_reopening_restores_it(isolated):
    from store import follow_ups

    fid = follow_ups.record_follow_up(kind="application_update", company="Virtana")
    follow_ups.resolve_follow_up(fid)
    follow_ups.reopen_follow_up(fid)
    assert follow_ups.open_count() == 1


def test_resolving_something_that_does_not_exist_is_an_error(isolated):
    from store import follow_ups

    with pytest.raises(ValueError):
        follow_ups.resolve_follow_up(9999)


# ── routing from the mailbox ─────────────────────────────────────────────────

def test_an_application_update_with_no_tracker_row_still_reaches_the_user(isolated):
    """The common case: the user applied through Cutshort, not through us."""
    from outcomes import capture
    from store import follow_ups

    results = capture.process_messages(
        [{"subject": "Questionnaire still pending from Virtana",
          "body": "Please complete it.", "sender": "voila@alerts.cutshort.io"}],
        applications=[],
    )
    assert results and results[0]["company"] == "Virtana"
    assert results[0]["follow_up"] is True
    assert follow_ups.open_count() == 1


def test_a_known_application_is_advanced_and_followed_up(isolated):
    """When the tracker does know it, the employer engaging means 'responded'."""
    from outcomes import capture
    from store import db as store
    from store import follow_ups

    with store.db() as conn:
        # applications.job_id is a real foreign key — which is exactly why an
        # application made outside this tool cannot live in that table at all.
        conn.execute(
            "INSERT INTO jobs (id, url, source, company, title) "
            "VALUES ('j1', 'https://x.test/j1', 'test', 'Virtana', 'SRE')"
        )
        conn.execute(
            "INSERT INTO applications (job_id, company, role, status) "
            "VALUES ('j1', 'Virtana', 'SRE', 'applied')"
        )
        app_id = conn.execute("SELECT id FROM applications").fetchone()["id"]

    results = capture.process_messages(
        [{"subject": "Questionnaire still pending from Virtana", "body": "",
          "sender": "voila@alerts.cutshort.io"}],
        applications=[{"id": app_id, "job_id": "j1", "company": "Virtana",
                       "role": "SRE", "status": "applied"}],
    )
    assert results
    with store.db() as conn:
        status = conn.execute(
            "SELECT status FROM applications WHERE id = ?", (app_id,)
        ).fetchone()["status"]
    assert status == "responded"
    assert follow_ups.open_count() == 1


def test_a_rejection_settles_it_and_creates_no_follow_up(isolated):
    """A terminal outcome outranks 'needs action' — there is nothing left to do."""
    from outcomes import capture
    from store import follow_ups

    capture.process_messages(
        [{"subject": "Your application to Virtana",
          "body": "Unfortunately we are not moving forward.",
          "sender": "talent@virtana.com"}],
        applications=[],
    )
    assert follow_ups.open_count() == 0


def test_a_digest_never_becomes_a_follow_up(isolated):
    from outcomes import capture
    from store import follow_ups

    capture.process_messages(
        [{"subject": "10+ Top Tech Jobs Curated for You", "body": "",
          "sender": "info@hirist.tech"}],
        applications=[],
    )
    assert follow_ups.open_count() == 0


def test_purging_a_job_cannot_delete_the_evidence(isolated):
    """job_id is deliberately not a foreign key — see the migration."""
    from store import db as store
    from store import follow_ups

    follow_ups.record_follow_up(
        kind="application_update", company="Virtana", job_id="does-not-exist")
    assert follow_ups.open_count() == 1
    with store.db() as conn:
        conn.execute("DELETE FROM jobs WHERE id = 'does-not-exist'")
    assert follow_ups.open_count() == 1
