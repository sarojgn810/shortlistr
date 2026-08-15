"""Is this person plausibly connected to hiring for this role?

LinkedIn's "People you can reach out to" panel suggests whoever you share
history with, not whoever is hiring. On an SRE opening at MishiPay it offered an
"Enterprise Revenue and Commercial Leader — SaaS & AI", flagged as a company
alum from a former employer. Messaging him about a reliability role would have
been a cold sales pitch to a sales director.

At one message that is an awkward afternoon. Automated across a pipeline it is
a reputation, so a resolved contact is scored before anything is drafted.
"""

from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))

ROLE = "Site Reliability Engineer"


def verdict(title, role=ROLE, **over):
    from prep.contact_relevance import assess_contact

    return assess_contact({"title": title, **over}, role=role)


# ── People worth writing to ──────────────────────────────────────────────────

@pytest.mark.parametrize(
    "title",
    [
        "Engineering Manager, Platform",
        "Director of Engineering",
        "Head of Infrastructure",
        "Technical Recruiter",
        "Senior Talent Acquisition Partner",
        "VP Engineering",
        "Staff Site Reliability Engineer",
        "CTO",
    ],
)
def test_plausible_contacts_pass(title):
    assert verdict(title).relevant is True, title


# ── People who should stop the draft ─────────────────────────────────────────

@pytest.mark.parametrize(
    "title",
    [
        # The exact profile LinkedIn surfaced on the MishiPay SRE posting.
        "Enterprise Revenue and Commercial Leader | SaaS & AI | Aligning Sales, "
        "Marketing & Customer Success to Drive Scalable, Profitable Growth",
        "Account Executive",
        "Regional Sales Director",
        "Head of Marketing",
        "Customer Success Manager",
        "Financial Controller",
        "Brand Partnerships Lead",
    ],
)
def test_unrelated_functions_are_flagged(title):
    result = verdict(title)

    assert result.relevant is False, title
    # The reason is shown next to a skipped draft, so it has to explain itself.
    assert result.reason


def test_a_recruiter_passes_even_without_the_role_words():
    # Recruiters never carry the job's own title, and they are often the right
    # person to write to.
    assert verdict("Talent Acquisition Specialist").relevant is True


def test_sales_engineer_is_not_an_engineering_contact():
    # "Sales Engineer" contains "engineer" and is a revenue role. Matching on
    # the word alone is how a sales director gets an SRE pitch.
    assert verdict("Sales Engineer").relevant is False


def test_missing_title_is_uncertain_not_approved():
    result = verdict("")

    # Unknown is not the same as fine. Without a title there is no basis to
    # send, and the user can still send it by hand.
    assert result.relevant is False
    assert "title" in result.reason.lower()


def test_alumni_suggestions_are_not_treated_as_hiring_contacts():
    from prep.contact_relevance import assess_contact

    result = assess_contact(
        {"title": "Enterprise Revenue Leader", "source": "linkedin_suggestion",
         "note": "Company alum from Wipro"},
        role=ROLE,
    )

    assert result.relevant is False


def test_verdict_carries_the_title_for_display():
    result = verdict("Account Executive")

    assert "Account Executive" in result.reason
