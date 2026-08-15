"""What must be true before an application can be sent unattended.

Auto-apply removes the human from the moment of sending, so everything the
human used to check by looking at the screen has to become an assertion. The
failure this guards against is not a crash — it is a form that submits with
default values and burns that company for the user permanently.

Approval stays the gate. These checks sit behind it: a job the user never
approved is never a candidate, whatever else is true of it.
"""

from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))

# Job ids are 16 hex chars (store.status._JOB_ID_RE); anything else is
# rejected before the pipeline is even consulted.
JOB = "a1b2c3d4e5f60718"
JOB2 = "b1b2c3d4e5f60719"


@pytest.fixture
def store(monkeypatch, tmp_path):
    import config

    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    import store.db as db

    monkeypatch.setattr(db, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(db, "DB_PATH", os.path.join(str(tmp_path), "shortlistr.db"))
    db.init_db()
    return db


def add_job(db, job_id=JOB, *, status="approved", url="https://boards.greenhouse.io/x/jobs/1"):
    with db.db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO jobs (id,url,source,company,title,jd_text) VALUES (?,?,?,?,?,?)",
            (job_id, url, "test", "Acme", "SRE", "x" * 400))
        conn.execute("INSERT INTO pipeline (job_id,status) VALUES (?,?)", (job_id, status))
    return job_id


@pytest.fixture
def ready(monkeypatch):
    """Everything present — individual tests remove one thing."""
    from apply import submit

    monkeypatch.setattr(submit, "_cv_pdf_for", lambda jid: "/tmp/cv.pdf")
    monkeypatch.setattr(submit, "_cover_letter_for", lambda jid: "Dear hiring manager, ...")
    return submit


@pytest.mark.parametrize("status", ["pending", "evaluated", "skipped", "submitted"])
def test_refuses_any_job_the_user_did_not_approve(store, ready, status):
    add_job(store, status=status)

    check = ready.check_preconditions(JOB)

    # Approval is the gate and only a human passes it. "evaluated" is the
    # dangerous one: it means the machine formed an opinion and nobody agreed.
    assert check["ok"] is False
    assert "approve" in check["reason"].lower()


def test_allows_an_approved_job_with_everything_present(store, ready):
    add_job(store, status="approved")

    assert ready.check_preconditions(JOB)["ok"] is True


def test_refuses_without_a_tailored_cv(store, ready, monkeypatch):
    add_job(store)
    monkeypatch.setattr(ready, "_cv_pdf_for", lambda jid: None)

    check = ready.check_preconditions(JOB)

    assert check["ok"] is False
    assert "cv" in check["reason"].lower() or "resume" in check["reason"].lower()


def test_refuses_without_a_cover_letter(store, ready, monkeypatch):
    add_job(store)
    monkeypatch.setattr(ready, "_cover_letter_for", lambda jid: "")

    check = ready.check_preconditions(JOB)

    assert check["ok"] is False
    assert "cover letter" in check["reason"].lower()


def test_refuses_a_job_with_no_url(store, ready):
    with store.db() as conn:
        conn.execute(
            "INSERT INTO jobs (id,url,source,company,title,jd_text) VALUES (?,?,?,?,?,?)",
            (JOB2, "", "test", "Acme", "SRE", "x" * 400))
        conn.execute("INSERT INTO pipeline (job_id,status) VALUES (?,?)", (JOB2, "approved"))

    assert ready.check_preconditions(JOB2)["ok"] is False


def test_refuses_a_link_only_posting(store, ready, monkeypatch):
    # Some sources give a listing page with no fillable form. Auto-submitting
    # there would mean clicking something arbitrary on an unknown page.
    add_job(store, url="https://www.linkedin.com/jobs/view/123")
    from apply import channels

    monkeypatch.setattr(channels, "is_link_only", lambda url, source: True)

    check = ready.check_preconditions(JOB)

    assert check["ok"] is False


def test_reason_is_specific_enough_to_act_on(store, ready, monkeypatch):
    add_job(store)
    monkeypatch.setattr(ready, "_cover_letter_for", lambda jid: "")

    reason = ready.check_preconditions(JOB)["reason"]

    # This surfaces in the UI next to a job that did not go out. "Not ready"
    # would leave the user with nothing to do about it.
    assert len(reason) > 15
    assert "cover letter" in reason.lower()


def test_missing_job_is_refused_not_crashed(store, ready):
    check = ready.check_preconditions("nope")

    assert check["ok"] is False
