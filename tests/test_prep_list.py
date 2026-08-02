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
    monkeypatch.setattr(
        "prep.ownership.load_owned_prep",
        lambda job_id, prep_dir=None, url="": (None, None),
    )
    monkeypatch.setattr(
        "api.prep_bundle._find_cv_for_job",
        lambda job_id, company: None,
    )
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
    from prep.ownership import front_matter, prep_path_for_job

    job_id = "cccccccccccccccc"
    guide = prep_path_for_job(job_id, prep_dir)
    with open(guide, "w", encoding="utf-8") as f:
        f.write(front_matter(job_id=job_id, owner="test@example.com") + "# Prep\n")

    monkeypatch.setattr(
        "store.prep_drafts.get_cover_letter_draft",
        lambda job_id, tenant_id="default": None,
    )
    monkeypatch.setattr(
        "api.prep_bundle._find_cv_for_job",
        lambda job_id, company: None,
    )
    monkeypatch.setattr(
        "prep.ownership.owner_key",
        lambda: "test@example.com",
    )

    _seed(store, job_id, "Acme", "Staff Engineer", "approved")
    items = prep_bundle.list_prep_summaries()
    acme = next(i for i in items if i["job_id"] == job_id)
    assert acme["has_prep_guide"] is True
    assert acme["ready"] is True
    assert "fit_label" in acme
