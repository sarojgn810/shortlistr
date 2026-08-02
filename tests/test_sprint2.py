"""Tests for sprint 2: diff API, export applications, evaluated filter."""

from __future__ import annotations

import os
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))


@pytest.fixture
def isolated_data_dir(monkeypatch):
    tmp = tempfile.mkdtemp()
    import config

    monkeypatch.setattr(config, "DATA_DIR", tmp)
    import store.db as db_mod

    monkeypatch.setattr(db_mod, "DATA_DIR", tmp)
    monkeypatch.setattr(db_mod, "DB_PATH", os.path.join(tmp, "shortlistr.db"))
    return tmp


def test_compute_diff_endpoint_shape(isolated_data_dir, monkeypatch):
    from models.job import JobRecord
    from prep.diff import compute_diff
    from store import db as store

    store.init_db()
    job = JobRecord(
        url="https://boards.greenhouse.io/acme/jobs/1",
        source="test",
        company="Acme",
        title="SRE",
        jd_text="Kubernetes SRE role.",
    )
    store.upsert_job(job)
    data = compute_diff(job.job_id)
    assert data["job_id"] == job.job_id
    assert "diff" in data
    assert data["company"] == "Acme"


def test_fetch_evaluated_jobs(isolated_data_dir, monkeypatch):
    import config
    from api.jobs_api import fetch_jobs
    from models.job import JobRecord
    from store import db as store

    # Pin targeting: this asserts status retrieval, not the fit gate, and must
    # not depend on the live config/profile.yml threshold.
    monkeypatch.setattr(config, "MIN_FIT_SCORE", 0)

    store.init_db()
    job = JobRecord(
        url="https://boards.greenhouse.io/acme/jobs/2",
        source="test",
        company="Acme",
        title="Platform",
        jd_text="Terraform.",
    )
    store.upsert_job(job)
    store.add_to_pipeline(job.job_id)
    with store.db() as conn:
        conn.execute(
            "UPDATE pipeline SET status = 'evaluated' WHERE job_id = ?",
            (job.job_id,),
        )
    with store.db() as conn:
        rows = fetch_jobs(conn, status="evaluated", resolve_missing=False)
    assert any(r["id"] == job.job_id for r in rows)


def test_export_applications_writes_file(isolated_data_dir, monkeypatch):
    from paths import applications_file
    import config

    apps_path = os.path.join(isolated_data_dir, "applications.md")
    monkeypatch.setattr(config, "DATA_DIR", isolated_data_dir)

    import paths

    monkeypatch.setattr(paths, "applications_file", lambda: apps_path)

    from models.job import JobRecord
    from store import db as store
    from store.export import export_applications

    store.init_db()
    job = JobRecord(
        url="https://boards.greenhouse.io/acme/jobs/3",
        source="test",
        company="Acme",
        title="DevOps",
        jd_text="CI/CD",
    )
    store.upsert_job(job)
    store.add_to_pipeline(job.job_id)
    with store.db() as conn:
        conn.execute(
            "UPDATE pipeline SET status = 'evaluated' WHERE job_id = ?",
            (job.job_id,),
        )

    path = export_applications()
    assert os.path.isfile(path)
    text = open(path, encoding="utf-8").read()
    assert "Acme" in text
    assert "DevOps" in text
