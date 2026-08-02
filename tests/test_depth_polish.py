"""Tests for prep bundle and ATS strategies."""

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
    import store.db as db_mod

    monkeypatch.setattr(config, "DATA_DIR", tmp)
    monkeypatch.setattr(db_mod, "DATA_DIR", tmp)
    monkeypatch.setattr(db_mod, "DB_PATH", os.path.join(tmp, "shortlistr.db"))
    prep = os.path.join(tmp, "interview-prep")
    out = os.path.join(tmp, "output")
    os.makedirs(prep, exist_ok=True)
    os.makedirs(out, exist_ok=True)
    monkeypatch.setattr(config, "PREP_DIR", prep)
    monkeypatch.setattr(config, "OUTPUT_DIR", out)
    return tmp


def test_get_prep_bundle_cover_letter(isolated_data_dir):
    from api.prep_bundle import get_prep_bundle
    from models.job import JobRecord
    from store import db as store

    store.init_db()
    job = JobRecord(
        url="https://boards.greenhouse.io/acme/jobs/9",
        source="import",
        company="Acme",
        title="Staff SRE",
        jd_text="Kubernetes Terraform on-call",
    )
    store.upsert_job(job)
    bundle = get_prep_bundle(job.job_id, generate=False)
    assert bundle["cover_letter"]["body"]
    assert bundle["job_id"] == job.job_id


def test_find_cv_pdf_empty(isolated_data_dir):
    from apply.ats_strategies import find_cv_pdf

    assert find_cv_pdf("Acme") is None
