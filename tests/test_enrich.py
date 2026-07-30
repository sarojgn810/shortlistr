"""Tests for job enrichment and API serialization."""

from __future__ import annotations

import json
import os
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))

from store.enrich import company_title_from_url, enrich_job_dict, is_placeholder, prettify_company


def test_is_placeholder():
    assert is_placeholder("Unknown")
    assert is_placeholder("")
    assert not is_placeholder("Acme Corp")


def test_company_from_greenhouse_url():
    company, _ = company_title_from_url(
        "https://boards.greenhouse.io/datadog/jobs/1234567"
    )
    assert company == "Datadog"


def test_enrich_from_eval_json():
    job = {
        "company": "Unknown",
        "title": "Unknown",
        "url": "https://boards.greenhouse.io/acme/jobs/1",
        "result_json": json.dumps(
            {
                "company": "Acme AI",
                "role": "Staff Engineer",
                "legitimacy": "verified",
                "blocks": {"B": "Strong fit for platform roles.", "A": "LLM not configured — template only."},
            }
        ),
    }
    out = enrich_job_dict(job)
    assert out["company"] == "Acme AI"
    assert out["title"] == "Staff Engineer"
    assert out["title"] != "LLM not configured"
    assert out["eval_template_only"] is True


def test_prettify_datadoghq():
    assert prettify_company("datadoghq") == "Datadog"
    assert prettify_company("sumologic") == "Sumo Logic"


@pytest.fixture
def isolated_data_dir(monkeypatch):
    tmp = tempfile.mkdtemp()
    import config
    monkeypatch.setattr(config, "DATA_DIR", tmp)
    import store.db as db_mod
    monkeypatch.setattr(db_mod, "DATA_DIR", tmp)
    monkeypatch.setattr(db_mod, "DB_PATH", os.path.join(tmp, "shortlistr.db"))
    return tmp


def test_persist_resolved_job_strips_html(isolated_data_dir):
    from store.enrich import persist_resolved_job
    from models.job import JobRecord
    from store import db as store

    store.init_db()
    job = JobRecord(
        url="https://boards.greenhouse.io/acme/jobs/1",
        source="import",
        company="Unknown",
        title="Unknown",
    )
    store.upsert_job(job)
    persist_resolved_job(
        job.job_id,
        {"company": "Acme", "title": "Engineer", "jd_snippet": "<p>Hello <b>world</b></p>"},
    )
    with store.db() as conn:
        row = conn.execute("SELECT jd_text FROM jobs WHERE id = ?", (job.job_id,)).fetchone()
    assert "Hello world" in row["jd_text"]
    assert "<p>" not in row["jd_text"]


def test_fetch_jobs_enriched(isolated_data_dir, monkeypatch):
    import config
    from api.jobs_api import fetch_jobs
    from models.job import JobRecord
    from store import db as store

    # This test is about enrichment, not targeting. Pin the fit threshold so it
    # does not read the live config/profile.yml, where a real min_fit_score
    # would filter out this unscored fixture.
    monkeypatch.setattr(config, "MIN_FIT_SCORE", 0)

    store.init_db()
    job = JobRecord(
        url="https://boards.greenhouse.io/vector/jobs/99",
        source="import",
        company="Unknown",
        title="Unknown",
        jd_text="Build ML systems.",
    )
    store.upsert_job(job)
    store.add_to_pipeline(job.job_id)

    with store.db() as conn:
        rows = fetch_jobs(conn, status="inbox")
    assert len(rows) == 1
    assert rows[0]["company"] == "Vector"
    assert "jd_text" not in rows[0]


def test_fetch_jobs_resolve_optional(isolated_data_dir, monkeypatch):
    import config
    from api.jobs_api import fetch_jobs
    from models.job import JobRecord
    from store import db as store

    monkeypatch.setattr(config, "MIN_FIT_SCORE", 0)

    store.init_db()
    job = JobRecord(
        url="https://boards.greenhouse.io/vector/jobs/99",
        source="import",
        company="Unknown",
        title="Unknown",
        jd_text="Build ML systems.",
    )
    store.upsert_job(job)
    store.add_to_pipeline(job.job_id)

    with store.db() as conn:
        rows = fetch_jobs(conn, status="inbox", resolve_missing=False)
    assert len(rows) == 1
    assert rows[0]["company"] == "Vector"
