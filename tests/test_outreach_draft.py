"""Outreach drafted from the posting's own requirements.

The message that already existed said "happy to share a short note on fit" —
true of every candidate for every job, and therefore worth nothing to the person
reading it. Since evaluation now records which of a posting's hard requirements
the CV answers *and quotes the line that answers it*, a draft can name two or
three of them instead.

Two rules hold throughout. Nothing is claimed that the evidence does not carry —
these go out under the user's name to someone who can check. And an unmet
requirement is never dressed up as met; if there is nothing solid to say, the
draft stays generic rather than inventing something.
"""

from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))

MUST_HAVES = [
    {"req": "5+ years running production Kubernetes", "met": True,
     "evidence": "Ran production Kubernetes on AWS EKS for 4 years"},
    {"req": "Terraform for infrastructure as code", "met": True,
     "evidence": "Terraform, CloudFormation, Ansible"},
    {"req": "Go or Rust for tooling", "met": False, "evidence": ""},
    {"req": "On-call ownership of SLOs", "met": True,
     "evidence": "SLO / SLI / Error Budgets, Incident & On-Call Management"},
]


def draft(**over):
    from prep.outreach_draft import draft_grounded_outreach

    kwargs = {
        "company": "MishiPay",
        "role": "Site Reliability Engineer",
        "contact_name": "Priya Raman",
        "candidate_name": "Saroj Nayak",
        "must_haves": MUST_HAVES,
    }
    kwargs.update(over)
    return draft_grounded_outreach(**kwargs)


def test_names_the_role_and_company():
    body = draft()

    assert "MishiPay" in body
    assert "Site Reliability Engineer" in body


def test_greets_the_contact_by_first_name():
    assert draft().startswith("Hi Priya")


def test_cites_requirements_the_cv_actually_answers():
    body = draft().lower()

    # The specifics are the whole point — this is what a generic note cannot say.
    assert "kubernetes" in body or "terraform" in body


def test_never_claims_an_unmet_requirement():
    body = draft().lower()

    # "Go or Rust" is unmet. Mentioning it as experience would be a false claim
    # to someone who will ask about it in the first screen.
    assert "rust" not in body
    assert not any(phrase in body for phrase in ("go or rust", "experience in go"))


def test_falls_back_to_a_plain_note_when_there_is_no_evidence():
    body = draft(must_haves=[])

    assert "MishiPay" in body
    assert body.strip()
    # Better a short honest note than an invented specific.
    assert "kubernetes" not in body.lower()


def test_all_unmet_produces_no_invented_specifics():
    unmet = [{"req": r["req"], "met": False, "evidence": ""} for r in MUST_HAVES]

    body = draft(must_haves=unmet).lower()

    assert "kubernetes" not in body
    assert "terraform" not in body


def test_stays_short_enough_to_be_read():
    body = draft()

    # A recruiter skims. Past a short paragraph or two it goes unread, and
    # length is what tempts a model into padding.
    assert len(body) < 900, len(body)
    assert body.count("\n\n") <= 4


def test_signs_off_as_the_candidate():
    assert draft().rstrip().endswith("Saroj Nayak")


def test_missing_contact_name_still_reads_naturally():
    body = draft(contact_name="")

    assert body.startswith("Hi,")
    assert "None" not in body


def test_never_claims_to_have_applied():
    body = draft().lower()

    # The tool must not state something about the user's actions that may not
    # be true — they may be reaching out before applying.
    for claim in ("i have applied", "i've applied", "my application is"):
        assert claim not in body


@pytest.mark.parametrize("junk", ["", None, "not a list"])
def test_malformed_evidence_is_survivable(junk):
    body = draft(must_haves=junk)

    assert "MishiPay" in body


def test_reads_cleanly_on_real_requirement_text():
    """Truncating requirement prose produced sentences no one would send.

    Real output from the first attempt: "The posting asks for production cloud
    infrastructure, site Reliability Engineering (SRE) and datadog, that is the
    work I have been doing" — broken capitalisation, a stray comma, and a
    severed parenthetical "(Python and experience designing APIs".
    """
    real = [
        {"req": "Deep understanding of Site Reliability Engineering (SRE), SLOs, "
                "Error Budgets and Incident Management",
         "met": True, "evidence": "SLO / SLI / Error Budgets"},
        {"req": "Proficiency in at least one modern language (Python, Go)",
         "met": True, "evidence": "Python, Bash"},
        {"req": "Hands-on experience with Datadog, Prometheus, Grafana or ELK",
         "met": True, "evidence": "Prometheus, Grafana"},
    ]

    body = draft(must_haves=real)

    assert "site Reliability" not in body, "lowercased a proper noun"
    assert body.count("(") == body.count(")"), f"unbalanced parentheses: {body}"
    assert ", that is" not in body, "comma splice"
    assert " ," not in body and ",," not in body


def test_real_length_requirements_do_not_become_a_wall():
    """Requirements in the wild are long. Three of them in one sentence is unreadable.

    Taken from a live MishiPay posting — the first draft produced a 300-character
    sentence that no recruiter would finish.
    """
    real = [
        {"req": "Hands-on experience managing production cloud infrastructure",
         "met": True, "evidence": "AWS EKS in production"},
        {"req": "Deep understanding of Site Reliability Engineering (SRE), SLOs, "
                "Error Budgets and Incident Management",
         "met": True, "evidence": "SLO / SLI / Error Budgets"},
        {"req": "Hands-on experience with Datadog, Azure Monitor, Prometheus, "
                "Grafana or ELK",
         "met": True, "evidence": "Prometheus, Grafana"},
    ]

    body = draft(must_haves=real)
    paragraphs = [p for p in body.split("\n\n") if p.strip()]

    # Whatever it says, no paragraph should outgrow a glance.
    longest = max(len(p) for p in paragraphs)
    assert longest < 190, f"{longest} chars: {max(paragraphs, key=len)}"


def test_uses_at_most_a_few_specifics():
    many = [
        {"req": f"Requirement {i}", "met": True, "evidence": f"did thing {i}"}
        for i in range(12)
    ]

    body = draft(must_haves=many)

    # Listing everything reads as a CV dump, not a note from a person.
    assert body.lower().count("requirement") <= 3
