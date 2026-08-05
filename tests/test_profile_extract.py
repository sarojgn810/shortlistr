"""Tests for best-effort résumé → profile field extraction."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "automation"))

from cv.profile_extract import extract_profile_fields  # noqa: E402


SAMPLE = """# Alex Candidate
**alex@example.com | +1 555 010 1234 | Seattle, USA | linkedin.com/in/alex-candidate | github.com/alex-candidate**

## Professional Summary
Senior Software Engineer with 9+ years building observability and
platform tooling for high-scale systems.

## Professional Experience
### Senior Software Engineer, Acme Corp | 2019 - Present
- Built Prometheus + Grafana stacks.

### Platform Engineer, Globex | 2015 - 2019
- Owned Kubernetes clusters.

## Education
B.S. Computer Science — 2015
"""


def test_extracts_core_contact_fields():
    out = extract_profile_fields(SAMPLE)
    assert out["name"] == "Alex Candidate"
    assert out["email"] == "alex@example.com"
    assert out["phone"].replace(" ", "") == "+15550101234"
    assert "linkedin.com/in/alex-candidate" in out["linkedin"]
    assert "github.com/alex-candidate" in out["github"]
    assert out["linkedin"].startswith("https://")


def test_extracts_location_and_years():
    out = extract_profile_fields(SAMPLE)
    assert out["location"] == "Seattle, USA"
    # Explicit "9+ years" in the summary wins.
    assert out["years_exp"] == 9


def test_infers_preferred_locations_from_city():
    out = extract_profile_fields(SAMPLE)
    assert "region" not in out
    assert out["preferred_locations"] == ["Seattle"]


def test_real_world_contact_line_with_middot_and_bold():
    # Mirrors the PDF-ingested contact format: middle-dot separators, markdown
    # bold wrapper, city without an explicit country before it. The details are
    # invented — this repo is meant to be cloned, and the author's real phone
    # number and address have no business travelling with it.
    md = (
        "# ASHA MENON\n\n"
        "**+91 90000 00000 · asha.menon@example.com · "
        "linkedin.com/in/asha-menon · github.com/asha-menon · Bangalore, India**\n\n"
        "## PROFESSIONAL SUMMARY\nSite Reliability Engineer with 9+ years.\n"
    )
    out = extract_profile_fields(md)
    assert out["email"] == "asha.menon@example.com"
    assert out["location"] == "Bangalore, India"
    assert out["preferred_locations"] == ["Bangalore"]


def test_non_india_location_leaves_region_unset():
    md = (
        "# Jane Doe\n\n**jane@x.com · Berlin, Germany**\n\n"
        "## Summary\nEngineer with 5 years.\n"
    )
    out = extract_profile_fields(md)
    assert out["location"] == "Berlin, Germany"
    assert out["preferred_locations"] == ["Berlin"]


def test_extracts_recent_title():
    """The résumé's own titles lead the list.

    Asserted by containment rather than exact equality: targeting now also
    carries adjacent roles, and pinning the whole list to a literal is what let
    a fresh clone ship with five titles while this test stayed green.
    """
    titles = extract_profile_fields(SAMPLE)["target_titles"]
    assert titles[0] == "Senior Software Engineer"
    for expected in ("Software Engineer", "Platform Engineer"):
        assert expected in titles, titles
    assert len(titles) == len(set(titles))


def test_extracts_multiple_titles_without_duplicates():
    md = """# Pat Doe
pat@example.com

## Experience
### Lead DevOps Engineer | Example Co | 2021 - Present
- work
### Senior DevOps Engineer | Previous Co | 2018 - 2021
- work
### Platform Engineer | Older Co | 2015 - 2018
- work
"""
    titles = extract_profile_fields(md)["target_titles"]
    assert titles[0] == "Lead DevOps Engineer"
    for expected in ("DevOps Engineer", "Senior DevOps Engineer", "Platform Engineer"):
        assert expected in titles, titles
    assert len(titles) == len(set(titles)), f"duplicates: {titles}"


def test_years_from_date_span_when_no_explicit_claim():
    md = """# Jane Doe
jane@x.com

## Experience
### Engineer, A | 2010 - Present
- work
"""
    out = extract_profile_fields(md)
    assert out["years_exp"] >= 14  # 2010 → current year


def test_empty_and_thin_input_returns_no_noise():
    assert extract_profile_fields("") == {}
    out = extract_profile_fields("just some text with no structure")
    # Must not invent contact fields.
    assert "email" not in out
    assert "phone" not in out


def test_omits_missing_fields():
    md = "# Bob Smith\n\n## Summary\nA person.\n"
    out = extract_profile_fields(md)
    assert out.get("name") == "Bob Smith"
    assert "email" not in out
    assert "linkedin" not in out
