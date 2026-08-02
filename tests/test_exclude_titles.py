"""Excluding a role by title, without excluding it by job description.

Widening target_titles to reach adjacent roles (Platform / Infrastructure /
DevOps Engineer) also lets in the management and PM versions of those same
words. The obvious place to filter those back out is deal_breakers — and that
would have been a bad mistake.

deal_breakers are matched against `title + jd_text`. On 161 real postings:

    "manager" in title or JD body : 27
    "manager" in the title        :  6

So filtering management roles through deal_breakers would have zeroed 21 genuine
SRE jobs for saying "you will report to the engineering manager". exclude_titles
matches the title only.

It also closes a leak that predates the widening: "Site Reliability Engineering
Manager" contains "Site Reliability Engineer", so it passed even the narrow list.
"""

from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))


@pytest.fixture
def scored(monkeypatch):
    """score_job with a known profile: 9 years, SRE targets, no salary floor."""
    import config as cfg
    from processors import job_filter

    # Pin the targets too. Another test in the suite reloads the profile, and
    # without this the title gate rejects before the exclusion is ever reached —
    # which passed alone and failed in a full run.
    monkeypatch.setattr(cfg, "SEARCH_KEYWORDS",
                        ["Site Reliability Engineer", "SRE", "Platform Engineer"])
    monkeypatch.setattr(cfg, "EXCLUDE_TITLES", ["Manager", "Director", "Head of"])
    monkeypatch.setattr(cfg, "DEAL_BREAKERS", [])
    monkeypatch.setattr(cfg, "MIN_SALARY_INR_LPA", 0)
    monkeypatch.setattr(cfg, "MIN_SALARY_USD", 0)
    monkeypatch.setattr(cfg, "REMOTE_STRICT", False)
    monkeypatch.setattr(cfg, "CANDIDATE", {"years_exp": 9})

    def _run(title: str, jd: str = "kubernetes terraform on-call prometheus"):
        return job_filter.score_job({"title": title, "jd_text": jd,
                                     "location": "Remote", "company": "Acme"})
    return _run


def test_a_management_title_is_dropped(scored):
    out = scored("Site Reliability Engineering Manager")
    assert out["fit_score"] == 0
    assert "excluded title" in out["fit_reason"], out.get("fit_reason")


def test_the_individual_contributor_role_survives(scored):
    out = scored("Senior Site Reliability Engineer")
    assert out["fit_score"] > 0, out.get("fit_reason")


def test_a_manager_in_the_job_description_is_not_a_manager_role(scored):
    """The whole reason this is not a deal_breaker.

    27 of 161 real postings mention a manager in the body; only 6 are management
    roles. Matching the body would discard the other 21.
    """
    out = scored(
        "Site Reliability Engineer",
        jd="You will report to the Engineering Manager and work with the "
           "Director of Platform. kubernetes terraform on-call prometheus",
    )
    assert out["fit_score"] > 0, out.get("fit_reason")


def test_matching_is_case_insensitive(scored):
    assert scored("PLATFORM ENGINEERING MANAGER")["fit_score"] == 0


def test_a_substring_of_a_real_word_does_not_trigger(scored):
    """"management" must not read as "manager"."""
    out = scored("Site Reliability Engineer, Configuration Management")
    assert out["fit_score"] > 0, out.get("fit_reason")


def test_no_exclusions_configured_changes_nothing(scored, monkeypatch):
    import config as cfg

    monkeypatch.setattr(cfg, "EXCLUDE_TITLES", [])
    out = scored("Site Reliability Engineering Manager")
    assert out["fit_score"] > 0, out.get("fit_reason")


def test_an_empty_entry_is_ignored(scored, monkeypatch):
    """A blank line in the profile must not match every title and stop the scan."""
    import config as cfg

    monkeypatch.setattr(cfg, "EXCLUDE_TITLES", ["", "   "])
    out = scored("Senior Site Reliability Engineer")
    assert out["fit_score"] > 0, out.get("fit_reason")


# ── the profile actually shipped ─────────────────────────────────────────────
#
# config/profile.yml is the user layer and is gitignored, so on a fresh clone or
# in CI it does not exist. These assert the local profile is configured the way
# the widening intends; they skip rather than fail where there is no profile.

PROFILE = os.path.join(ROOT, "config", "profile.yml")
needs_profile = pytest.mark.skipif(not os.path.isfile(PROFILE),
                                   reason="config/profile.yml is user-local")



@needs_profile
def test_the_shipped_profile_reaches_the_adjacent_roles():
    """The point of widening: these were dropped at the first gate before."""
    import yaml
    from pipeline.filter import _title_matches

    f = yaml.safe_load(open(PROFILE))["filters"]
    titles = f["target_titles"]
    for role in ("Senior Infrastructure Engineer (Core Infra)",
                 "Platform Engineer",
                 "Senior DevOps Engineer - fully remote",
                 "Staff Site Reliability Engineer"):
        assert _title_matches(role, titles), role


@needs_profile
def test_the_shipped_profile_still_rejects_unrelated_work():
    import yaml
    from pipeline.filter import _title_matches

    f = yaml.safe_load(open(PROFILE))["filters"]
    for role in ("Account Executive", "Registered Nurse", "Financial Analyst"):
        assert not _title_matches(role, f["target_titles"]), role


@needs_profile
def test_management_words_are_not_in_deal_breakers():
    """Guards the mistake this whole module exists to prevent."""
    import yaml

    f = yaml.safe_load(open(PROFILE))["filters"]
    body_matched = [d.lower() for d in (f.get("deal_breakers") or [])]
    for word in ("manager", "director", "head of"):
        assert word not in body_matched, (
            f"'{word}' in deal_breakers matches the JD body and would discard "
            "genuine engineering roles; it belongs in exclude_titles"
        )
