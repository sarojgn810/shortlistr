"""Scheduling a submission, and being able to take it back.

The undo window is the only moment between deciding and something irreversible
happening, so it has to hold even when the process does not. The awkward case is
a restart mid-window: the queued row survives, and whatever picks it up next
must not treat "queued a moment ago" as "the window has passed".

It fails closed. A submission that is dropped costs one click to retry; a
submission that fires inside its own undo window cannot be retrieved.
"""

from __future__ import annotations

import json
import os
import sys
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))

JOB = "a1b2c3d4e5f60718"


@pytest.fixture
def store(monkeypatch, tmp_path):
    import config

    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    import store.db as db

    monkeypatch.setattr(db, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(db, "DB_PATH", os.path.join(str(tmp_path), "shortlistr.db"))
    db.init_db()
    with db.db() as conn:
        conn.execute(
            "INSERT INTO jobs (id,url,source,company,title,jd_text) VALUES (?,?,?,?,?,?)",
            (JOB, "https://boards.greenhouse.io/x/jobs/1", "test", "Acme", "SRE", "x" * 400))
        conn.execute("INSERT INTO pipeline (job_id,status) VALUES (?,?)", (JOB, "approved"))
    return db


@pytest.fixture
def ready(monkeypatch):
    from apply import submit

    monkeypatch.setattr(submit, "_cv_pdf_for", lambda jid: "/tmp/cv.pdf")
    monkeypatch.setattr(submit, "_cover_letter_for", lambda jid: "Dear team, ...")
    return submit


def test_schedules_a_submission_for_an_approved_job(store, ready):
    from apply import autoapply

    result = autoapply.schedule_submission(JOB, delay_seconds=60, start_timer=False)

    assert result["scheduled"] is True
    assert result["submit_after"] > time.time()


def test_refuses_to_schedule_when_preconditions_fail(store, ready, monkeypatch):
    from apply import autoapply, submit

    monkeypatch.setattr(submit, "_cover_letter_for", lambda jid: "")

    result = autoapply.schedule_submission(JOB, delay_seconds=60, start_timer=False)

    assert result["scheduled"] is False
    assert "cover letter" in result["reason"].lower()
    # Nothing queued means nothing to cancel later.
    assert autoapply.pending_submissions() == []


def test_pending_submission_is_visible_for_the_countdown(store, ready):
    from apply import autoapply

    autoapply.schedule_submission(JOB, delay_seconds=60, start_timer=False)

    pending = autoapply.pending_submissions()

    assert len(pending) == 1
    assert pending[0]["job_id"] == JOB
    assert pending[0]["seconds_left"] > 0


def test_cancel_removes_it(store, ready):
    from apply import autoapply

    autoapply.schedule_submission(JOB, delay_seconds=60, start_timer=False)

    assert autoapply.cancel_submission(JOB)["cancelled"] is True
    assert autoapply.pending_submissions() == []


def test_cancelling_nothing_is_not_an_error(store, ready):
    from apply import autoapply

    assert autoapply.cancel_submission(JOB)["cancelled"] is False


def test_scheduling_twice_does_not_double_submit(store, ready):
    from apply import autoapply

    autoapply.schedule_submission(JOB, delay_seconds=60, start_timer=False)
    autoapply.schedule_submission(JOB, delay_seconds=60, start_timer=False)

    # Two queued rows would mean two applications to the same posting.
    assert len(autoapply.pending_submissions()) == 1


def test_worker_refuses_to_send_inside_the_undo_window(store, ready, monkeypatch):
    from apply import autoapply

    sent = []
    monkeypatch.setattr(autoapply, "_send", lambda job_id, **kw: sent.append(job_id) or {"ok": True})

    payload = {"job_id": JOB, "submit_after": time.time() + 3600}

    with pytest.raises(Exception):
        autoapply.run_scheduled_submission(payload)

    # A restart must not turn "queued a moment ago" into "send it now". Failing
    # closed costs a retry; sending early cannot be undone.
    assert sent == []


def test_worker_sends_once_the_window_has_passed(store, ready, monkeypatch):
    from apply import autoapply

    sent = []
    monkeypatch.setattr(autoapply, "_send", lambda job_id, **kw: sent.append(job_id) or {"ok": True})

    autoapply.run_scheduled_submission({"job_id": JOB, "submit_after": time.time() - 1})

    assert sent == [JOB]


def test_worker_rechecks_preconditions_at_send_time(store, ready, monkeypatch):
    from apply import autoapply, submit

    sent = []
    monkeypatch.setattr(autoapply, "_send", lambda job_id, **kw: sent.append(job_id) or {"ok": True})
    # The user un-approved it during the window, or the CV was deleted. The
    # state at scheduling time is not the state at sending time.
    monkeypatch.setattr(submit, "_cv_pdf_for", lambda jid: None)

    with pytest.raises(Exception):
        autoapply.run_scheduled_submission({"job_id": JOB, "submit_after": time.time() - 1})

    assert sent == []


def test_queue_row_carries_the_deadline(store, ready):
    from apply import autoapply

    autoapply.schedule_submission(JOB, delay_seconds=60, start_timer=False)

    with store.db() as conn:
        row = conn.execute(
            "SELECT task_type, payload_json FROM worker_queue WHERE task_type = 'auto_apply'"
        ).fetchone()

    # The deadline lives in the row, not only in a timer thread, so it survives
    # the process that created it.
    assert json.loads(row["payload_json"])["submit_after"] > time.time()
