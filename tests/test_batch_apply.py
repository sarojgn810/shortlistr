"""B1 — batch apply authorization + mark-submitted."""

from __future__ import annotations

import os
import sys
import tempfile

import pytest

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


def _seed(url):
    from models.job import JobRecord, job_id_from_url
    from store import db

    jid = job_id_from_url(url)
    db.upsert_job(JobRecord(url=url, source="test", company="Acme", title="SRE", job_id=jid))
    db.add_to_pipeline(jid, "evaluated")
    return jid


def test_apply_batch_gated_then_approves_and_mark_submitted(monkeypatch):
    pytest.importorskip("fastapi")
    _isolate(monkeypatch)
    from agent import registry
    from api.main import create_app
    from fastapi.testclient import TestClient
    from store import db

    db.init_db()
    j1 = _seed("https://boards.greenhouse.io/acme/jobs/1")
    j2 = _seed("https://boards.greenhouse.io/acme/jobs/2")
    monkeypatch.setattr(registry, "_autopilot_tools", lambda t: [])

    client = TestClient(create_app())

    # no confirm → gated
    assert client.post("/jobs/apply-batch", json={"job_ids": [j1, j2]}).status_code == 403

    # confirm → approved + queued
    r = client.post("/jobs/apply-batch", json={"job_ids": [j1, j2], "confirm": True})
    assert r.status_code == 200 and r.json()["count"] == 2

    # record a submission → application applied
    r2 = client.post(f"/jobs/{j1}/mark-submitted")
    assert r2.status_code == 200 and r2.json()["status"] == "applied"


def test_apply_channel_detection():
    from api.jobs_api import apply_channel_for

    assert apply_channel_for({"company_email": "jobs@acme.com", "url": "x"}) == "email"
    assert apply_channel_for({"url": "https://x"}) == "form"
    assert apply_channel_for({}) == "manual"


def test_send_application_gated_then_sends(monkeypatch):
    pytest.importorskip("fastapi")
    _isolate(monkeypatch)
    from agent import registry
    from api.main import create_app
    from fastapi.testclient import TestClient
    from models.job import JobRecord, job_id_from_url
    from store import db
    import processors.email_sender as es

    db.init_db()
    url = "https://boards.greenhouse.io/acme/jobs/9"
    jid = job_id_from_url(url)
    db.upsert_job(JobRecord(url=url, source="test", company="Acme", title="SRE",
                            job_id=jid, company_email="jobs@acme.com"))
    db.add_to_pipeline(jid, "approved")
    monkeypatch.setattr(registry, "_autopilot_tools", lambda t: [])
    monkeypatch.setattr(es, "send_application_email", lambda **k: True)

    client = TestClient(create_app())
    assert client.post(f"/jobs/{jid}/send-application", json={}).status_code == 403
    r = client.post(f"/jobs/{jid}/send-application", json={"confirm": True})
    assert r.status_code == 200 and r.json()["sent"] is True
