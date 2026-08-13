"""Assembling an outreach draft: who to write to, and what to say.

Ties together the three pieces — resolved contacts, the relevance guard, and
the evidence-grounded drafter. The ordering is the point: a contact is judged
*before* a message is written for them, so an irrelevant one produces a reason
rather than a draft nobody should send.

Nothing here sends anything. It returns text for the user to read.
"""

from __future__ import annotations

import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))

JOB = "a1b2c3d4e5f60718"

MUST_HAVES = [
    {"req": "Production Kubernetes at scale", "met": True, "evidence": "Ran Kubernetes on EKS"},
    {"req": "Terraform for IaC", "met": True, "evidence": "Terraform, Ansible"},
    {"req": "Rust for systems work", "met": False, "evidence": ""},
]


@pytest.fixture
def store(monkeypatch, tmp_path):
    import config

    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    import store.db as db

    monkeypatch.setattr(db, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(db, "DB_PATH", os.path.join(str(tmp_path), "shortlistr.db"))
    db.init_db()
    with db.db() as conn:
        conn.execute(
            "INSERT INTO jobs (id,url,source,company,title,jd_text) VALUES (?,?,?,?,?,?)",
            (JOB, "https://x.test/j", "test", "MishiPay", "Site Reliability Engineer", "x" * 400))
        conn.execute(
            "INSERT INTO eval_results (job_id,schema_version,score,legitimacy,result_json) "
            "VALUES (?,?,?,?,?)",
            (JOB, "v1", 4.4, "likely", json.dumps({"must_haves": MUST_HAVES})))
    return db


def people(*rows):
    return {"people": list(rows), "emails": []}


def test_drafts_for_a_plausible_contact(store, monkeypatch):
    from prep import outreach_service

    monkeypatch.setattr(outreach_service, "_resolved", lambda jid: people(
        {"full_name": "Priya Raman", "title": "Engineering Manager, Platform",
         "source": "company_site"}))

    result = outreach_service.build_outreach(JOB)

    assert result["ok"] is True
    assert result["contact"]["full_name"] == "Priya Raman"
    assert "Priya" in result["draft"]
    # Grounded in the evaluation, not generic.
    assert "Kubernetes" in result["draft"] or "Terraform" in result["draft"]


def test_refuses_an_irrelevant_contact_without_drafting(store, monkeypatch):
    from prep import outreach_service

    monkeypatch.setattr(outreach_service, "_resolved", lambda jid: people(
        {"full_name": "Biplob Bora",
         "title": "Enterprise Revenue and Commercial Leader | SaaS & AI",
         "source": "linkedin_suggestion", "note": "Company alum from Wipro"}))

    result = outreach_service.build_outreach(JOB)

    assert result["ok"] is False
    assert not result["draft"], "wrote a message for someone who should be skipped"
    assert result["reason"]


def test_prefers_the_relevant_contact_over_an_earlier_irrelevant_one(store, monkeypatch):
    from prep import outreach_service

    monkeypatch.setattr(outreach_service, "_resolved", lambda jid: people(
        {"full_name": "Biplob Bora", "title": "Regional Sales Director", "source": "x"},
        {"full_name": "Priya Raman", "title": "Head of Infrastructure", "source": "x"},
    ))

    result = outreach_service.build_outreach(JOB)

    # Resolution order is confidence, not suitability — the first hit is often
    # the loudest profile rather than the right one.
    assert result["contact"]["full_name"] == "Priya Raman"


def test_reports_when_no_contact_was_found(store, monkeypatch):
    from prep import outreach_service

    monkeypatch.setattr(outreach_service, "_resolved", lambda jid: people())

    result = outreach_service.build_outreach(JOB)

    assert result["ok"] is False
    assert not result["draft"]
    assert "contact" in result["reason"].lower()


def test_falls_back_to_a_plain_note_without_an_evaluation(store, monkeypatch):
    from prep import outreach_service

    with store.db() as conn:
        conn.execute("DELETE FROM eval_results")
    monkeypatch.setattr(outreach_service, "_resolved", lambda jid: people(
        {"full_name": "Priya Raman", "title": "Engineering Manager", "source": "x"}))

    result = outreach_service.build_outreach(JOB)

    assert result["ok"] is True
    assert "MishiPay" in result["draft"]
    # No evidence means no invented specifics.
    assert "Kubernetes" not in result["draft"]


def test_never_reports_having_sent_anything(store, monkeypatch):
    from prep import outreach_service

    monkeypatch.setattr(outreach_service, "_resolved", lambda jid: people(
        {"full_name": "Priya Raman", "title": "Engineering Manager", "source": "x"}))

    result = outreach_service.build_outreach(JOB)

    # This module drafts. Sending is the user's, through a gated channel.
    assert "sent" not in result
    assert result.get("draft")


def test_missing_job_is_handled(store):
    from prep import outreach_service

    result = outreach_service.build_outreach("ffffffffffffffff")

    assert result["ok"] is False


# ── Details that only showed up against real resolved data ───────────────────


def test_picks_the_email_for_the_chosen_person(store, monkeypatch):
    from prep import outreach_service

    # cr_email_candidate links to a person by person_id. Matching on full_name
    # silently found nothing, so every draft said "(no email resolved)" even
    # with eight candidates sitting in the table.
    monkeypatch.setattr(outreach_service, "_resolved", lambda jid: {
        "people": [{"person_id": 17, "full_name": "Vishal Kanchan",
                    "title": "Engineering Manager", "source": "title_ladder"}],
        "emails": [
            {"person_id": 99, "email": "someone.else@entrupy.com", "final_score": 0.9,
             "verify_status": "unverified"},
            {"person_id": 17, "email": "vkanchan@entrupy.com", "final_score": 0.52,
             "verify_status": "unverified"},
            {"person_id": 17, "email": "vishal.kanchan@entrupy.com", "final_score": 0.63,
             "verify_status": "unverified"},
        ],
    })

    result = outreach_service.build_outreach(JOB)

    assert result["email"] == "vishal.kanchan@entrupy.com", "wrong person or weaker candidate"


def test_says_when_an_address_is_only_a_guess(store, monkeypatch):
    from prep import outreach_service

    monkeypatch.setattr(outreach_service, "_resolved", lambda jid: {
        "people": [{"person_id": 17, "full_name": "Vishal Kanchan",
                    "title": "Engineering Manager"}],
        "emails": [{"person_id": 17, "email": "vishal.kanchan@entrupy.com",
                    "final_score": 0.63, "verify_status": "unverified"}],
    })

    result = outreach_service.build_outreach(JOB)

    # These are pattern guesses (first.last@, flast@ …). Presenting one as fact
    # invites a bounce, and repeated bounces hurt the sender.
    assert result["email_verified"] is False


def test_shouty_profile_name_is_not_used_as_a_signature(store, monkeypatch):
    from prep import outreach_service

    # cv extraction stores the name as it appears on the résumé, in caps.
    monkeypatch.setattr(outreach_service, "_candidate_name", lambda: "ASHA MENON")
    monkeypatch.setattr(outreach_service, "_resolved", lambda jid: {
        "people": [{"person_id": 1, "full_name": "Priya Raman", "title": "Engineering Manager"}],
        "emails": [],
    })

    result = outreach_service.build_outreach(JOB)

    assert "ASHA MENON" not in result["draft"]
    assert "Asha Menon" in result["draft"]


def test_mixed_case_names_are_left_alone(store, monkeypatch):
    from prep import outreach_service

    monkeypatch.setattr(outreach_service, "_candidate_name", lambda: "Mary-Jane O'Brien")
    monkeypatch.setattr(outreach_service, "_resolved", lambda jid: {
        "people": [{"person_id": 1, "full_name": "Priya Raman", "title": "Engineering Manager"}],
        "emails": [],
    })

    result = outreach_service.build_outreach(JOB)

    assert "Mary-Jane O'Brien" in result["draft"]
