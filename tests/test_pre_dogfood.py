"""Pre-dogfood gap fixes — resume source, discovery relevance, PDF engine."""

from __future__ import annotations

import os
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUTOMATION = os.path.join(ROOT, "automation")
sys.path.insert(0, AUTOMATION)


@pytest.fixture
def isolated(monkeypatch):
    """Isolate DATA_DIR, OUTPUT_DIR, and SHORTLISTR_ROOT so resume/job state is sandboxed."""
    tmp = tempfile.mkdtemp()
    import config
    import store.db as db_mod

    out = os.path.join(tmp, "output")
    os.makedirs(out, exist_ok=True)
    monkeypatch.setattr(config, "DATA_DIR", tmp)
    monkeypatch.setattr(config, "OUTPUT_DIR", out)
    monkeypatch.setattr(config, "SHORTLISTR_ROOT", tmp)
    monkeypatch.setattr(db_mod, "DATA_DIR", tmp)
    monkeypatch.setattr(db_mod, "DB_PATH", os.path.join(tmp, "shortlistr.db"))
    return tmp


# ── Resume source ────────────────────────────────────────────────────────────

def test_resolve_resume_prefers_uploaded_by_default(isolated):
    from apply.ats_strategies import resolve_resume_pdf, uploaded_resume_pdf

    uploaded = os.path.join(isolated, "resume.pdf")
    with open(uploaded, "wb") as f:
        f.write(b"%PDF-1.4 uploaded")
    tailored = os.path.join(isolated, "output", "Acme-ats-classic-2026-06-30.pdf")
    with open(tailored, "wb") as f:
        f.write(b"%PDF-1.4 tailored")

    assert uploaded_resume_pdf() == uploaded
    # default resume_source is "uploaded"
    assert resolve_resume_pdf("Acme") == uploaded


def test_resolve_resume_generated_prefers_tailored(isolated):
    from apply.ats_strategies import resolve_resume_pdf
    from store.settings import set_cv_settings

    with open(os.path.join(isolated, "resume.pdf"), "wb") as f:
        f.write(b"%PDF-1.4 uploaded")
    tailored = os.path.join(isolated, "output", "Acme-ats-classic-2026-06-30.pdf")
    with open(tailored, "wb") as f:
        f.write(b"%PDF-1.4 tailored")

    set_cv_settings({"resume_source": "generated"})
    assert resolve_resume_pdf("Acme") == tailored


def test_resolve_resume_falls_back_when_missing(isolated):
    from apply.ats_strategies import resolve_resume_pdf
    from store.settings import set_cv_settings

    # generated requested but no tailored exists -> fall back to uploaded
    uploaded = os.path.join(isolated, "resume.pdf")
    with open(uploaded, "wb") as f:
        f.write(b"%PDF-1.4 uploaded")
    set_cv_settings({"resume_source": "generated"})
    assert resolve_resume_pdf("Acme") == uploaded


# ── Discovery relevance filter ───────────────────────────────────────────────

def _seed(url, relevance, *, fit_score=50):
    from models.job import JobRecord
    from store import db as store

    job = JobRecord(
        url=url, source="aggregators", company="Acme", title="X",
        metadata={"discovery_relevance": relevance},
    )
    store.upsert_job(job)
    store.add_to_pipeline(job.job_id)
    with store.db() as conn:
        conn.execute("UPDATE jobs SET fit_score = ? WHERE id = ?", (fit_score, job.job_id))
    return job.job_id


def test_relevance_filter_hides_off_target_by_default(isolated):
    from api.jobs_api import fetch_jobs
    from store import db as store

    store.init_db()
    rel_id = _seed("https://x.co/relevant", "relevant", fit_score=55)
    off_id = _seed("https://x.co/offtarget", "off_target", fit_score=55)

    with store.db() as conn:
        default_ids = {j["id"] for j in fetch_jobs(conn, status="pending")}
        all_ids = {j["id"] for j in fetch_jobs(conn, status="pending", relevance="all")}

    assert rel_id in default_ids
    assert off_id not in default_ids       # hidden by default
    assert {rel_id, off_id} <= all_ids     # both shown with relevance=all


def test_relevance_filter_hides_low_fit_relevant_jobs_by_default(isolated):
    from api.jobs_api import fetch_jobs
    from store import db as store

    store.init_db()
    strong_id = _seed("https://x.co/strong", "relevant", fit_score=55)
    weak_id = _seed("https://x.co/weak", "relevant", fit_score=0)

    with store.db() as conn:
        default_ids = {j["id"] for j in fetch_jobs(conn, status="pending")}
        all_ids = {j["id"] for j in fetch_jobs(conn, status="pending", relevance="all")}

    assert strong_id in default_ids
    assert weak_id not in default_ids
    assert {strong_id, weak_id} <= all_ids


def test_fetch_jobs_exposes_discovery_relevance(isolated):
    from api.jobs_api import fetch_jobs
    from store import db as store

    store.init_db()
    _seed("https://x.co/relevant", "relevant", fit_score=55)
    with store.db() as conn:
        jobs = fetch_jobs(conn, status="pending")
    assert jobs and jobs[0]["discovery_relevance"] == "relevant"


# ── PDF engine (Playwright) — skip if Chromium unavailable ───────────────────

def test_pdf_from_html_renders(isolated):
    pytest.importorskip("playwright")
    from generate_pdf import generate_pdf_from_html

    html = "<!DOCTYPE html><html><body><h1>Alex Candidate</h1><p>Engineer</p></body></html>"
    out = os.path.join(isolated, "out.pdf")
    try:
        res = generate_pdf_from_html(html, out, full_sheet=True)
    except Exception as e:  # no chromium binary in this env
        pytest.skip(f"Playwright/Chromium unavailable: {e}")
    assert os.path.isfile(out)
    assert res["size"] > 0
    assert open(out, "rb").read(4) == b"%PDF"
