"""What an inbound job email means, not just whether it holds links.

Every subject here is real, from a week of one inbox. Ingestion used to ask one
question — "does this contain job URLs?" — so a stalled application and an
employer asking for you by name were both discarded as "no extractable URLs".
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "automation"))


# ── the taxonomy, on real subjects ───────────────────────────────────────────

@pytest.mark.parametrize("subject,expected", [
    # An employer is asking for this user specifically.
    ("Missed message from Blitzy?", "invite_to_apply"),
    ("Reminder: Principal Engineer at KnackLabs", "invite_to_apply"),
    ("Reminder: Senior Support Engineer at Virtana", "invite_to_apply"),
    ("Site Reliability Engineer 3 role at eBay: you would be a great fit!",
     "invite_to_apply"),
    ("Missed message from Quantiphi?", "invite_to_apply"),
    # An application of theirs is stalled and needs action.
    ("Questionnaire still pending from Virtana", "application_update"),
    ("Trying one last time - questionnaire pending from FAiHr", "application_update"),
    ("Complete your application for SRE", "application_update"),
    ("Action required: assessment invite", "application_update"),
    # A broadcast list.
    ("IT/Tech Jobs Picked for Your Experience", "job_digest"),
    ("IT/Tech Jobs that match your experience", "job_digest"),
    ("10+ Matching Jobs based on your preferences", "job_digest"),
    ("10+ Top Tech Jobs Curated for You", "job_digest"),
    ("Remotive Job Alert", "job_digest"),
    ("Associate Site Reliability Engineer at Shell and 11 more jobs", "job_digest"),
    ("Saroj Nayak, New Job Opportunities for Site Reliability Engineer", "job_digest"),
    ("Saroj Nayak, Unlock Your Potential: Jobs you might have missed", "job_digest"),
    # One named role.
    ("Hiring | AI Engineer at Tiger Analytics", "single_posting"),
    ("Staff Software Engineer, Reliability at Metropolis Healthcare", "single_posting"),
    ("2024_MS_EDE3_XC_SRE_DataEngineering @ Bosch Group", "single_posting"),
    ("✉️ Job | Forward Deployed Engineer (FDE) in Bengaluru", "single_posting"),
    # Noise.
    ("Be first to apply—with Neo", "marketing"),
    ("Still Searching? Your Perfect Job is Here!", "marketing"),
    ("hirist.tech Registration", "account_admin"),
    ("Verify your email address", "account_admin"),
])
def test_real_subjects_classify_correctly(subject, expected):
    from processors.email_intent import classify_intent

    assert classify_intent(subject).kind == expected


def test_only_mail_about_this_user_counts_as_inbound_interest():
    from processors.email_intent import classify_intent

    assert classify_intent("Missed message from Blitzy?").is_inbound_interest
    assert classify_intent("Questionnaire still pending from Virtana").is_inbound_interest
    assert not classify_intent("10+ Top Tech Jobs Curated for You").is_inbound_interest
    assert not classify_intent("Hiring | AI Engineer at Tiger").is_inbound_interest


def test_account_admin_outranks_the_job_words_around_it():
    """'Verify your email' from a job board is not a job, however it is dressed."""
    from processors.email_intent import classify_intent

    assert classify_intent("Verify your email address to see 10+ jobs").kind == "account_admin"


def test_a_pending_questionnaire_is_an_application_not_a_fresh_invite():
    """Both patterns match 'Reminder: questionnaire pending' — order decides."""
    from processors.email_intent import classify_intent

    assert classify_intent(
        "Reminder: questionnaire pending from Virtana"
    ).kind == "application_update"


def test_a_headline_role_plus_more_jobs_is_still_a_digest():
    from processors.email_intent import classify_intent

    assert classify_intent(
        "Associate Site Reliability Engineer at Shell and 11 more jobs"
    ).kind == "job_digest"


def test_an_empty_subject_is_unknown_not_a_crash():
    from processors.email_intent import classify_intent

    assert classify_intent("").kind == "unknown"
    assert classify_intent(None).kind == "unknown"


# ── company extraction ───────────────────────────────────────────────────────

@pytest.mark.parametrize("subject,company", [
    ("Missed message from Blitzy?", "Blitzy"),
    ("Questionnaire still pending from Virtana", "Virtana"),
    ("Reminder: Principal Engineer at KnackLabs", "KnackLabs"),
    ("Site Reliability Engineer 3 role at eBay: you would be a great fit!", "eBay"),
])
def test_company_is_pulled_out_of_the_subject(subject, company):
    from processors.email_intent import extract_company

    assert extract_company(subject) == company


def test_a_digest_tail_is_not_mistaken_for_an_employer():
    from processors.email_intent import extract_company

    assert extract_company("Associate SRE at Shell and 11 more jobs") != "11 more jobs"


# ── which link the invite is actually about ──────────────────────────────────

def test_the_matching_link_is_the_one_the_subject_names():
    """An invite carries the named role plus a related-jobs footer."""
    from processors.email_intent import link_matches_subject

    subject = "Site Reliability Engineer 3 role at eBay: you would be a great fit!"
    assert link_matches_subject(subject, "Site Reliability Engineer 3 Bengaluru")
    assert not link_matches_subject(subject, "Mainframe Developer Remote Easy Apply")


def test_a_company_match_is_enough():
    from processors.email_intent import link_matches_subject

    assert link_matches_subject("Reminder: Principal Engineer at KnackLabs",
                                "Some Role", company="KnackLabs India")


def test_the_company_name_alone_does_not_match_every_role():
    """Otherwise every link in a single-employer mail would look like the one."""
    from processors.email_intent import link_matches_subject

    assert not link_matches_subject("Reminder: Principal Engineer at KnackLabs",
                                    "Warehouse Associate")


def test_matching_needs_more_than_one_shared_word():
    from processors.email_intent import link_matches_subject

    # "engineer" alone is not enough to claim it is the same role.
    assert not link_matches_subject("Data Engineer role at Acme", "Sales Engineer")


# ── the ingestion contract ───────────────────────────────────────────────────

def _reader(subject: str, links_html: str):
    from mail.base import Message

    class R:
        name = "gmail"

        def search_recent(self, *, days, senders=()):
            return ["m1"]

        def fetch(self, mid):
            return Message(id=mid, sender="glassdoor <noreply@glassdoor.com>",
                           subject=subject, body=links_html)

    return R()


def test_only_the_named_role_is_flagged_inbound(monkeypatch):
    """The footer openings are ordinary discovery, not an employer asking."""
    from automation.processors import email_monitor as em

    monkeypatch.setattr(em, "_load_state", lambda: {})
    monkeypatch.setattr(em, "_save_state", lambda s: None)

    html = (
        '<a href="https://www.glassdoor.co.in/partner/jobListing.htm?a=1">'
        'Site Reliability Engineer 3 Bengaluru</a>'
        '<a href="https://www.glassdoor.co.in/partner/jobListing.htm?a=2">'
        'Mainframe Developer Remote</a>'
    )
    jobs = em.fetch_alert_job_records(
        reader=_reader(
            "Site Reliability Engineer 3 role at eBay: you would be a great fit!", html
        )
    )
    flagged = [j for j in jobs if (j.metadata or {}).get("inbound_interest")]
    assert len(jobs) == 2
    assert len(flagged) == 1
    assert "Reliability" in flagged[0].title


def test_a_digest_never_produces_inbound_interest(monkeypatch):
    from automation.processors import email_monitor as em

    monkeypatch.setattr(em, "_load_state", lambda: {})
    monkeypatch.setattr(em, "_save_state", lambda s: None)

    html = "".join(
        f'<a href="https://www.hirist.tech/j/role-{i}">Site Reliability Engineer {i}</a>'
        for i in range(4)
    )
    jobs = em.fetch_alert_job_records(
        reader=_reader("10+ Top Tech Jobs Curated for You", html)
    )
    assert jobs
    assert not any((j.metadata or {}).get("inbound_interest") for j in jobs)
    assert all((j.metadata or {}).get("email_intent") == "job_digest" for j in jobs)


def test_an_actionable_message_with_no_link_is_not_buried(monkeypatch):
    """A stalled questionnaire has no job URL — marking it 'empty' would hide it."""
    from automation.processors import email_monitor as em

    saved = {}
    monkeypatch.setattr(em, "_load_state", lambda: {})
    monkeypatch.setattr(em, "_save_state", lambda s: saved.update(s))

    em.fetch_alert_job_records(
        reader=_reader("Questionnaire still pending from Virtana", "<p>no links</p>")
    )
    assert saved.get("empty_ids") == [], "an application update was remembered as empty"
