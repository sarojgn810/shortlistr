"""Answering ATS screening questions from the profile and the CV.

These are answers on a real job application, so the governing rule is that an
unanswered question is fine and a wrong one is not. Leaving a field blank costs
the user a moment of typing; claiming experience they do not have can cost them
a rescinded offer, and it misrepresents them to an employer.

So every answer here traces to something the user actually wrote — a profile
setting, or a term that appears in their CV. Anything else returns None.
"""

from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))

PROFILE = {
    "work_authorization": "Authorized to work in India; no sponsorship required",
    "willing_to_relocate": "Open to discussion",
    "notice_period": "60 Days",
    "years_exp": "9",
    "location": "Bangalore, India",
    "country_of_residence": "India",
    "on_call_ok": "Yes",
    "worked_here_before": "No",
}

CV = """
Saroj Nayak — Site Reliability Engineer
Ran production Kubernetes on AWS EKS for 4 years. Terraform, Prometheus,
Grafana. Built CI/CD with GitLab. Python and Go for tooling.
"""


def answer(question, profile=None, cv=CV):
    from apply.screening import answer_for

    return answer_for(question, profile if profile is not None else PROFILE, cv)


# ── Sponsorship and authorisation ────────────────────────────────────────────

def test_sponsorship_question_reads_the_profile():
    said = answer("Will you now or in the future require sponsorship for employment?")
    assert said is not None
    assert said.lower().startswith("no")


def test_authorisation_question_reads_the_profile():
    said = answer("Are you legally authorized to work in this country?")
    assert said is not None
    assert said.lower().startswith("yes")


def test_sponsorship_unanswered_when_the_profile_is_silent():
    said = answer("Will you require visa sponsorship?", profile={})
    # Guessing here is guessing about someone's immigration status.
    assert said is None


# ── Experience questions, grounded in the CV ─────────────────────────────────

@pytest.mark.parametrize("tech", ["Kubernetes", "AWS", "Terraform", "Python"])
def test_says_yes_only_when_the_cv_shows_the_technology(tech):
    said = answer(f"Do you have hands-on experience with {tech}?")
    assert said is not None
    assert said.lower().startswith("yes")


@pytest.mark.parametrize("tech", ["Salesforce", "COBOL", "Figma"])
def test_declines_rather_than_claiming_absent_experience(tech):
    said = answer(f"Do you have hands-on experience with {tech}?")
    # Not "No" either: the CV is a highlight reel, not an exhaustive record, so
    # absence is not evidence. The user answers this one.
    assert said is None


def test_matches_technology_case_insensitively():
    assert answer("Do you have production experience with kubernetes?") is not None


@pytest.mark.parametrize(
    "asked,in_cv",
    [
        ("Golang", "Go"),          # the CV says "Go for tooling"
        ("K8s", "Kubernetes"),
        ("Amazon Web Services", "AWS"),
    ],
)
def test_follows_common_spellings_of_the_same_technology(asked, in_cv):
    # A posting saying "Golang" and a CV saying "Go" are talking about the same
    # thing; leaving that unanswered sends the user to fill a field they have
    # already evidenced.
    assert in_cv.lower() in CV.lower()
    said = answer(f"Do you have professional programming experience in {asked}?")
    assert (said or "").lower().startswith("yes"), asked


def test_country_falls_back_to_the_location_already_set():
    profile = {k: v for k, v in PROFILE.items() if k != "country_of_residence"}

    # "Bangalore, India" already says the country — reading it off is not a
    # guess, and asking for it again is friction.
    assert answer("What is your current country of residence?", profile=profile) == "India"


def test_country_fallback_declines_on_a_bare_city():
    profile = {**PROFILE, "country_of_residence": "", "location": "Bangalore"}

    # No comma, no country. Assuming one would put a fact on an application
    # that the user never stated.
    assert answer("What is your current country of residence?", profile=profile) is None


def test_country_question_asked_the_long_way_round():
    said = answer("Please choose the country in which you will be located if hired")
    assert (said or "").lower() == "india"


def test_ignores_a_technology_mentioned_only_in_the_question():
    said = answer("Do you have hands-on experience in Kubernetes or Mesos?", cv="No tech here.")
    assert said is None


# ── Straightforward profile lookups ──────────────────────────────────────────

def test_years_of_experience():
    assert "9" in (answer("How many years of experience do you have?") or "")


def test_notice_period():
    assert "60" in (answer("What is your notice period?") or "")


def test_country_of_residence():
    assert (answer("What is your current country of residence?") or "").lower() == "india"


def test_on_call_question():
    said = answer("Are you comfortable participating in an on-call rotation?")
    assert (said or "").lower().startswith("yes")


def test_worked_here_before():
    said = answer("Have you previously worked at or consulted for GitLab?")
    assert (said or "").lower().startswith("no")


def test_relocation():
    assert answer("Are you willing to relocate?") is not None


# ── Questions we must not answer ─────────────────────────────────────────────

@pytest.mark.parametrize(
    "question",
    [
        "Gender",
        "Are you Hispanic/Latino?",
        "Veteran Status",
        "Disability Status",
        "What is your race or ethnicity?",
    ],
)
def test_never_answers_demographic_questions(question):
    # These are voluntary EEO fields. They are the user's to answer or decline,
    # and a tool filling them in on their behalf is speaking for them about
    # protected characteristics.
    assert answer(question) is None


def test_unknown_question_returns_nothing():
    assert answer("What is your favourite database and why?") is None


def test_empty_question_is_safe():
    assert answer("") is None


def test_no_profile_and_no_cv_answers_nothing():
    assert answer("Do you have experience with AWS?", profile={}, cv="") is None
