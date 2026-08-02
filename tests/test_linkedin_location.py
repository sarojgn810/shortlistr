"""A job title is not a location, and a headline is not a name.

Both came from assigning preamble lines by position and accepting almost
anything. The location rule was "a line under 60 characters containing a comma",
which on a real profile produced:

    location: "**Site Reliability Engineer"

The name rule was "the first line", so a paste that starts at the headline —
common, because the name sits in an image — shifted every field by one: the
headline landed in name and the real headline was lost.
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))

from linkedin_optimizer.parser import (
    looks_like_location,
    looks_like_person_name,
    parse_profile_text,
)


# ── what is a location ───────────────────────────────────────────────────────

def test_real_locations_are_accepted():
    for value in ("Bengaluru, Karnataka, India", "Bengaluru", "Remote",
                  "San Francisco Bay Area", "London, United Kingdom",
                  "Greater Seattle Area"):
        assert looks_like_location(value), value


def test_a_job_title_is_not_a_location():
    """The exact value this bug put in the field, plus its relatives."""
    for value in ("**Site Reliability Engineer",
                  "Site Reliability Engineer",
                  "Senior DevOps Engineer, Platform",
                  "Engineering Manager, Infrastructure",
                  "Product Designer"):
        assert not looks_like_location(value), value


def test_a_headline_is_not_a_location():
    assert not looks_like_location("Site Reliability Engineer | AIOps · MLOps")


def test_contact_details_are_not_locations():
    for value in ("arjun.mehta@example.com", "+91 90000 00000",
                  "https://linkedin.com/in/arjun-mehta", "www.example.com"):
        assert not looks_like_location(value), value


def test_a_sentence_is_not_a_location():
    assert not looks_like_location(
        "Nine years of experience across SRE, DevOps and platform work")


# ── what is a name ───────────────────────────────────────────────────────────

def test_real_names_are_accepted():
    for value in ("ARJUN MEHTA", "Jane Doe", "Mary-Jane O'Connor", "Priya Raman"):
        assert looks_like_person_name(value), value


def test_a_headline_is_not_a_name():
    for value in ("Site Reliability Engineer | Forward Deployed Engineer",
                  "Product Designer",
                  "Bengaluru, Karnataka, India",
                  "hello@example.com"):
        assert not looks_like_person_name(value), value


# ── the profile as a whole ───────────────────────────────────────────────────

def test_a_profile_with_a_name_parses_in_order():
    out = parse_profile_text(
        "ARJUN MEHTA\n"
        "Site Reliability Engineer | AIOps\n"
        "Bengaluru, Karnataka, India\n"
        "About\nNine years of SRE work.\n"
    )
    assert out["name"] == "ARJUN MEHTA"
    assert out["headline"] == "Site Reliability Engineer | AIOps"
    assert out["location"] == "Bengaluru, Karnataka, India"


def test_a_paste_starting_at_the_headline_does_not_shift_everything():
    """No name line — the headline must stay the headline."""
    out = parse_profile_text(
        "Site Reliability Engineer | Forward Deployed Engineer\n"
        "Bengaluru, Karnataka, India\n"
        "About\nNine years.\n"
    )
    assert out["name"] == ""
    assert out["headline"] == "Site Reliability Engineer | Forward Deployed Engineer"
    assert out["location"] == "Bengaluru, Karnataka, India"


def test_a_profile_with_no_section_headers_still_parses():
    out = parse_profile_text(
        "ARJUN MEHTA\n"
        "Site Reliability Engineer | AIOps\n"
        "Bengaluru, Karnataka, India\n"
        "Nine years of SRE work.\n"
    )
    assert out["name"] == "ARJUN MEHTA"
    assert out["headline"] == "Site Reliability Engineer | AIOps"
    assert out["location"] == "Bengaluru, Karnataka, India"


def test_a_profile_with_no_location_leaves_it_empty():
    """Empty beats wrong — a filled-in title is worse than a blank field."""
    out = parse_profile_text(
        "ARJUN MEHTA\n"
        "Site Reliability Engineer | AIOps · MLOps · Agentic AI\n"
        "About\nNine years of SRE work.\n"
    )
    assert out["location"] == ""
    assert "Engineer" not in out["location"]


def test_markdown_emphasis_is_stripped_from_what_is_kept():
    out = parse_profile_text(
        "**Jane Doe**\nStaff Platform Engineer\nBerlin, Germany\nAbout\nHi.\n")
    assert out["name"] == "Jane Doe"
    assert out["location"] == "Berlin, Germany"
