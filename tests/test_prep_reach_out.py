"""Prep Reach out — JD contact extract + LinkedIn deep links (no paid enrichment)."""

from __future__ import annotations

import os
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))


def test_extract_email_linkedin_and_named_contact():
    from prep.reach_out import extract_contacts_from_text

    jd = """
    Site Reliability Engineer — Acme Corp

    Contact: Jordan Lee, Talent Acquisition
    Email jordan.lee@acme.com for questions.
    Recruiter LinkedIn: https://www.linkedin.com/in/jordan-lee-ta/

    Reach out to Sam Patel if you have role questions.
    """
    contacts = extract_contacts_from_text(jd, company="Acme Corp")
    emails = {c["email"].lower() for c in contacts if c.get("email")}
    assert "jordan.lee@acme.com" in emails
    urls = {c["linkedin_url"].rstrip("/").lower() for c in contacts if c.get("linkedin_url")}
    assert "https://www.linkedin.com/in/jordan-lee-ta" in urls
    names = {c["name"] for c in contacts if c.get("name")}
    assert any("Sam Patel" == n or "Jordan" in n for n in names)


def test_invented_careers_email_ignored_unless_in_jd():
    from prep.reach_out import extract_contacts_from_text

    jd = "Build reliable systems. No contact listed."
    contacts = extract_contacts_from_text(
        jd, company="Acme", company_email="careers@acme.com"
    )
    assert contacts == []

    jd2 = "Apply via careers@acme.com"
    contacts2 = extract_contacts_from_text(
        jd2, company="Acme", company_email="careers@acme.com"
    )
    assert any(c.get("email") == "careers@acme.com" for c in contacts2)


def test_linkedin_search_links_include_company():
    from prep.reach_out import linkedin_search_links

    links = linkedin_search_links("Red Hat", "SRE")
    assert len(links) >= 3
    assert all(u["url"].startswith("https://www.linkedin.com/") for u in links)
    assert any("Recruiter" in u["label"] for u in links)
    assert any("Hiring" in u["label"] for u in links)


def test_user_contact_overrides_jd_email():
    from prep.reach_out import extract_contacts_from_text, merge_contacts

    jd = extract_contacts_from_text("Email: jane@acme.com")
    merged = merge_contacts(
        jd,
        [
            {
                "name": "Jane Doe",
                "email": "jane@acme.com",
                "linkedin_url": "https://linkedin.com/in/janedoe",
            }
        ],
    )
    assert len(merged) == 1
    assert merged[0]["source"] == "user"
    assert merged[0]["name"] == "Jane Doe"
    assert "janedoe" in merged[0]["linkedin_url"]


def test_build_reach_out_in_prep_bundle(monkeypatch):
    tmp = tempfile.mkdtemp()
    import config
    import store.db as db_mod
    from models.job import JobRecord, job_id_from_url
    from store import db as store
    from api.prep_bundle import get_prep_bundle

    monkeypatch.setattr(config, "DATA_DIR", tmp)
    monkeypatch.setattr(config, "SHORTLISTR_ROOT", tmp, raising=False)
    monkeypatch.setattr(config, "SHORTLISTR_ROOT", tmp, raising=False)
    monkeypatch.setattr(config, "PREP_DIR", os.path.join(tmp, "interview-prep"))
    monkeypatch.setattr(config, "INTERVIEW_PREP_DIR", os.path.join(tmp, "interview-prep"))
    monkeypatch.setattr(config, "OUTPUT_DIR", os.path.join(tmp, "output"))
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
    os.makedirs(config.PREP_DIR, exist_ok=True)
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    open(config.CV_MD_PATH, "w", encoding="utf-8").write("# Ada\n\nSRE.\n")
    monkeypatch.setattr(db_mod, "DATA_DIR", tmp)
    monkeypatch.setattr(db_mod, "DB_PATH", os.path.join(tmp, "shortlistr.db"))
    store.init_db()

    url = "https://boards.greenhouse.io/acme/jobs/reach-out-1"
    jid = job_id_from_url(url)
    store.upsert_job(
        JobRecord(
            url=url,
            source="greenhouse",
            company="Acme",
            title="SRE",
            jd_text="Contact: Pat Recruiter — pat@acme.com\nhttps://www.linkedin.com/in/pat-recruiter/",
            job_id=jid,
            company_email="careers@acme.com",  # invented — not in JD alone as contact without match
            fit_score=70,
        )
    )
    store.add_to_pipeline(jid, "approved")

    bundle = get_prep_bundle(jid, generate=False)
    ro = bundle["reach_out"]
    assert ro["searches"]
    assert any(c.get("email") == "pat@acme.com" for c in ro["contacts"])
    assert "outreach_draft" in ro
    assert "do not scrape" in (ro.get("disclaimer") or "").lower() or "LinkedIn" in ro["disclaimer"]
