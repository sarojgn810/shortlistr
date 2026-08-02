"""O1 — outcome capture: classify inbound mail and transition application status."""

from __future__ import annotations

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))


def _isolate(monkeypatch):
    tmp = tempfile.mkdtemp()
    import config
    import store.db as db_mod

    monkeypatch.setattr(config, "DATA_DIR", tmp)
    monkeypatch.setattr(db_mod, "DATA_DIR", tmp)
    monkeypatch.setattr(db_mod, "DB_PATH", os.path.join(tmp, "shortlistr.db"))
    return tmp


def test_classify_outcome():
    from outcomes.capture import classify_outcome

    assert classify_outcome("Update", "Unfortunately we won't be proceeding.")[0] == "rejected"
    assert classify_outcome("Next steps", "Let's schedule a call this week")[0] == "interview"
    assert classify_outcome("Good news", "We are pleased to offer you the role")[0] == "offer"
    assert classify_outcome("Hi", "Thanks for applying, we'll be in touch")[0] is None


def test_process_messages_transitions_and_ignores_ambiguous(monkeypatch):
    _isolate(monkeypatch)
    from models.job import JobRecord, job_id_from_url
    from outcomes import capture
    from store import db, status

    db.init_db()
    url = "https://boards.greenhouse.io/acme/jobs/1"
    jid = job_id_from_url(url)
    db.upsert_job(JobRecord(url=url, source="test", company="Acme Corp", title="SRE", job_id=jid))
    status.upsert_application(jid, company="Acme Corp", role="SRE", score=4.0, status="applied")

    # high-confidence rejection mentioning the company → transition
    res = capture.process_messages([
        {"subject": "Your application to Acme Corp",
         "body": "Unfortunately we won't be proceeding with your candidacy.",
         "sender": "hr@acme.com"},
    ])
    assert len(res) == 1 and res[0]["to"] == "rejected" and res[0]["company"] == "Acme Corp"

    # a second, still-active application + ambiguous mail → no transition
    url2 = "https://boards.greenhouse.io/globex/jobs/2"
    jid2 = job_id_from_url(url2)
    db.upsert_job(JobRecord(url=url2, source="test", company="Globex", title="SRE", job_id=jid2))
    status.upsert_application(jid2, company="Globex", role="SRE", score=4.0, status="applied")
    res2 = capture.process_messages([
        {"subject": "hi", "body": "thanks for applying to Globex", "sender": "x@globex.com"},
    ])
    assert res2 == []


def test_match_application_requires_company_in_text():
    from outcomes.capture import match_application

    apps = [{"id": 1, "company": "Datadog", "status": "applied"}]
    assert match_application("Interview with Datadog next week", apps)["id"] == 1
    assert match_application("unrelated message", apps) is None
