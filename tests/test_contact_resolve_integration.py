"""Integration: resolve_job_contact with JD email, no network autocomplete."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "automation"))


@pytest.fixture()
def job_with_contact(monkeypatch, tmp_path):
    import config
    import store.db as db_mod
    from models.job import JobRecord
    from store import db as store

    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr(config, "DATA_DIR", str(data), raising=False)
    monkeypatch.setattr(db_mod, "DATA_DIR", str(data), raising=False)
    monkeypatch.setattr(db_mod, "DB_PATH", str(data / "shortlistr.db"), raising=False)

    # Avoid Clearbit / MX network in tests
    monkeypatch.setattr(
        "contacts.domain.autocomplete_domain",
        lambda *a, **k: "example.com",
    )
    monkeypatch.setattr(
        "contacts.domain.mx_lookup",
        lambda domain: ("google", ["aspmx.l.google.com"]),
    )

    store.init_db()
    job = JobRecord(
        url="https://careers.example.com/jobs/1",
        source="test",
        company="Example Corp",
        title="SRE",
        location="Bengaluru",
        jd_text="Reach out to Jane Doe (jane.doe@example.com), Talent Partner.",
    )
    store.upsert_jobs([job])
    return job.job_id


def test_resolve_finds_jd_email(job_with_contact, monkeypatch):
    from contacts.resolve import resolve_job_contact

    result = resolve_job_contact(
        job_with_contact,
        use_serp=False,
        use_github=False,
        verify=False,
    )
    assert result.get("status") in ("resolved", "person_no_email", "no_domain")
    emails = result.get("emails") or []
    assert any("jane.doe@example.com" in (e.get("email") or "") for e in emails)
    best = (result.get("summary") or {}).get("best") or emails[0]
    assert best.get("decision") in ("SEND_NOW", "VERIFY_FIRST", "REVIEW", "SKIP")
