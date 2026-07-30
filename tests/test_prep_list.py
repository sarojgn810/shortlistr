"""Prep list for the sidebar Prep page."""

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
    prep_dir = os.path.join(tmp, "interview-prep")
    os.makedirs(prep_dir, exist_ok=True)

    import config
    import store.db as db_mod
    import api.prep_bundle as prep_bundle

    monkeypatch.setattr(config, "DATA_DIR", tmp)
    monkeypatch.setattr(config, "SHORTLISTR_ROOT", tmp)
    monkeypatch.setattr(config, "PREP_DIR", prep_dir)
    monkeypatch.setattr(config, "INTERVIEW_PREP_DIR", prep_dir)
    monkeypatch.setattr(db_mod, "DATA_DIR", tmp)
    monkeypatch.setattr(db_mod, "DB_PATH", os.path.join(tmp, "shortlistr.db"))

    db_mod.init_db()
    return db_mod, prep_dir, prep_bundle


def _seed(store, job_id: str, company: str, title: str, status: str = "approved"):
    with store.db() as conn:
        conn.execute(
            "INSERT INTO jobs (id, url, title, company, location, source, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (job_id, f"https://example.com/{job_id}", title, company, "Remote", "test", "open"),
        )
        conn.execute(
            "INSERT INTO pipeline (job_id, status, added_at) VALUES (?, ?, datetime('now'))",
            (job_id, status),
        )


def test_list_prep_includes_approved_jobs(isolated, monkeypatch):
    store, _prep_dir, prep_bundle = isolated
    monkeypatch.setattr(prep_bundle, "_latest_prep_path", lambda company, role: None)
    monkeypatch.setattr("apply.ats_strategies.find_cv_pdf", lambda company="": None)
    monkeypatch.setattr(
        "store.prep_drafts.get_cover_letter_draft",
        lambda job_id, tenant_id="default": None,
    )

    _seed(store, "aaaaaaaaaaaaaaaa", "Acme", "Staff Engineer", "approved")
    _seed(store, "bbbbbbbbbbbbbbbb", "Beta", "SRE", "pending")

    items = prep_bundle.list_prep_summaries()
    ids = {i["job_id"] for i in items}
    assert "aaaaaaaaaaaaaaaa" in ids
    assert "bbbbbbbbbbbbbbbb" not in ids
    acme = next(i for i in items if i["job_id"] == "aaaaaaaaaaaaaaaa")
    assert acme["company"] == "Acme"
    assert acme["ready"] is False


def test_list_prep_marks_ready_when_guide_exists(isolated, monkeypatch):
    store, prep_dir, prep_bundle = isolated
    guide = os.path.join(prep_dir, "Acme-Staff_Engineer-2026-07-30.md")
    with open(guide, "w", encoding="utf-8") as f:
        f.write("# Prep\n")

    monkeypatch.setattr(
        prep_bundle,
        "_latest_prep_path",
        lambda company, role: guide if "Acme" in company else None,
    )
    monkeypatch.setattr("apply.ats_strategies.find_cv_pdf", lambda company="": None)
    monkeypatch.setattr(
        "store.prep_drafts.get_cover_letter_draft",
        lambda job_id, tenant_id="default": None,
    )

    _seed(store, "cccccccccccccccc", "Acme", "Staff Engineer", "approved")
    items = prep_bundle.list_prep_summaries()
    acme = next(i for i in items if i["job_id"] == "cccccccccccccccc")
    assert acme["has_prep_guide"] is True
    assert acme["ready"] is True
