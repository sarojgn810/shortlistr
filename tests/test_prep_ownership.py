"""Prep guides must belong to the live profile + job_id."""

from __future__ import annotations

import os
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))


@pytest.fixture
def prep_iso(monkeypatch):
    tmp = tempfile.mkdtemp()
    prep_dir = os.path.join(tmp, "interview-prep")
    out_dir = os.path.join(tmp, "output")
    os.makedirs(prep_dir, exist_ok=True)
    os.makedirs(out_dir, exist_ok=True)

    import config
    import store.db as db_mod

    monkeypatch.setattr(config, "DATA_DIR", tmp)
    monkeypatch.setattr(config, "AUTOJOB_ROOT", tmp, raising=False)
    monkeypatch.setattr(config, "SHORTLISTR_ROOT", tmp, raising=False)
    monkeypatch.setattr(config, "PREP_DIR", prep_dir)
    monkeypatch.setattr(config, "INTERVIEW_PREP_DIR", prep_dir)
    monkeypatch.setattr(config, "OUTPUT_DIR", out_dir)
    monkeypatch.setattr(config, "CV_MD_PATH", os.path.join(tmp, "cv.md"))
    monkeypatch.setattr(
        config,
        "CANDIDATE",
        {
            "name": "Ada Example",
            "email": "ada@example.com",
            "years_exp": "5",
            "location": "",
            "linkedin": "",
            "github": "",
            "phone": "",
            "resume_path": "",
        },
        raising=False,
    )
    monkeypatch.setattr(db_mod, "DATA_DIR", tmp)
    monkeypatch.setattr(db_mod, "DB_PATH", os.path.join(tmp, "autojob.db"))
    db_mod.init_db()

    with open(config.CV_MD_PATH, "w", encoding="utf-8") as f:
        f.write("# Ada Example\n\n**ada@example.com**\n\n## PROFESSIONAL SUMMARY\n\nSRE.\n")

    return tmp, prep_dir, out_dir, db_mod


def test_foreign_company_prep_file_is_ignored(prep_iso):
    _tmp, prep_dir, _out, _db = prep_iso
    from prep.ownership import load_owned_prep

    foreign = os.path.join(prep_dir, "Acme-Staff_Engineer-2026-01-01.md")
    with open(foreign, "w", encoding="utf-8") as f:
        f.write(
            "---\njob_id: otherjobid123456\nowner: other@example.com\n---\n"
            "# Interview Prep — Acme\n**Prepared for:** Other Person\n"
            "## Your Proof Points\n- Other person's secret metric\n"
        )

    path, content = load_owned_prep("aaaaaaaaaaaaaaaa", url="https://example.com/acme")
    assert path is None
    assert content is None


def test_owned_job_prep_is_loaded(prep_iso):
    _tmp, prep_dir, _out, _db = prep_iso
    from prep.ownership import front_matter, load_owned_prep, prep_path_for_job

    jid = "bbbbbbbbbbbbbbbb"
    path = prep_path_for_job(jid, prep_dir)
    body = "# Interview Prep — Acme\n**Prepared for:** Ada Example\n"
    with open(path, "w", encoding="utf-8") as f:
        f.write(front_matter(job_id=jid, owner="ada@example.com", company="Acme") + body)

    got_path, content = load_owned_prep(jid)
    assert got_path == path
    assert content and "Ada Example" in content
    assert "other@example.com" not in content


def test_find_cv_pdf_does_not_return_unrelated(prep_iso):
    _tmp, _prep, out_dir, _db = prep_iso
    from apply.ats_strategies import find_cv_pdf

    stranger = os.path.join(out_dir, "OtherCo-2026-01-01.pdf")
    with open(stranger, "wb") as f:
        f.write(b"%PDF-1.4 fake")

    assert find_cv_pdf("Acme") is None
    assert find_cv_pdf("Acme", job_id="cccccccc") is None

    mine = os.path.join(out_dir, "cccccccc-Acme-2026-01-02.pdf")
    with open(mine, "wb") as f:
        f.write(b"%PDF-1.4 mine")
    assert find_cv_pdf("Acme", job_id="cccccccc") == mine


def test_generate_prep_stamps_owner_and_job(prep_iso):
    _tmp, prep_dir, _out, _db = prep_iso
    from processors.generate_prep import generate_prep_for_job
    from prep.ownership import parse_front_matter

    jid = "dddddddddddddddd"
    result = generate_prep_for_job(
        {
            "job_id": jid,
            "company": "Acme",
            "title": "SRE",
            "url": "https://example.com/acme",
            "jd_snippet": "SRE role",
            "fit_score": 72,
            "eval_score": 4.2,
        }
    )
    assert result["success"]
    assert result["path"].endswith(f"{jid}.md")
    raw = open(result["path"], encoding="utf-8").read()
    meta, body = parse_front_matter(raw)
    assert meta["job_id"] == jid
    assert meta["owner"] == "ada@example.com"
    assert "4.2/5" in body
    assert "Prepared for:** Ada Example" in body or "Prepared for: Ada Example" in body.replace(
        "**", ""
    )
