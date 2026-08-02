"""A résumé must be able to fill the profile fields you left blank.

Reported from a fresh Windows clone: onboarding "couldn't take Full Name, City,
few other details" from the uploaded résumé. Extraction was working — this was
two separate faults downstream of it.

First, a new install was not blank. `_default_profile()` returned
config/profile.example.yml, which is documentation for hand-editing and carries
a worked example: Jane Smith, San Francisco, +1 555 000 0000. So onboarding
opened pre-filled with a stranger's details.

Second, the résumé pass only filled identity when no profile existed yet.
Onboarding asks for the profile at step 1 and the résumé at step 2, so a profile
always exists by upload time. Between the two, every extracted value was
discarded as a conflict with data the user had never entered.
"""

from __future__ import annotations

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "automation"))

RESUME = {
    "name": "Arjun Mehta",
    "email": "arjun@example.com",
    "phone": "+91 90000 00000",
    "location": "Bengaluru",
    "linkedin": "https://linkedin.com/in/arjun-mehta",
    "github": "https://github.com/arjun-mehta",
    "years_exp": 7,
    "preferred_locations": ["Bengaluru"],
}


@pytest.fixture
def store(monkeypatch):
    import profile_store as ps

    monkeypatch.setattr(ps, "PROFILE_PATH", os.path.join(tempfile.mkdtemp(), "profile.yml"))
    return ps


# ── a fresh install is empty ─────────────────────────────────────────────────

def test_a_new_install_has_no_identity_prefilled(store):
    """The example file is documentation, not somebody's starting data."""
    p = store.get_profile_for_ui()
    for field in ("name", "email", "phone", "location", "linkedin", "github"):
        assert p[field] == "", f"{field} was pre-filled with {p[field]!r}"
    assert p["years_exp"] == 0


def test_the_example_person_never_reaches_a_user(store):
    p = store.get_profile_for_ui()
    blob = " ".join(str(v) for v in p.values()).lower()
    for leaked in ("jane smith", "janesmith", "san francisco", "555 000 0000"):
        assert leaked not in blob, f"example data leaked: {leaked}"


# ── the résumé fills what is blank ───────────────────────────────────────────

def test_a_resume_fills_fields_left_blank_at_step_one(store):
    """The reported bug: profile saved first, résumé uploaded second."""
    store.save_profile_from_ui(
        {"name": "Arjun", "email": "arjun@example.com", "target_titles": ["SRE"]})
    store.update_target_titles_from_resume(["Site Reliability Engineer"], extracted=RESUME)

    p = store.get_profile_for_ui()
    assert p["location"] == "Bengaluru"
    assert p["phone"] == "+91 90000 00000"
    assert p["linkedin"] == "https://linkedin.com/in/arjun-mehta"
    assert p["years_exp"] == 7


def test_what_the_user_typed_is_never_overwritten(store):
    """Filling blanks must not become correcting people."""
    store.save_profile_from_ui({
        "name": "Arjun", "email": "arjun@example.com",
        "location": "Mumbai", "phone": "+91 11111 11111",
        "target_titles": ["SRE"],
    })
    store.update_target_titles_from_resume(["SRE"], extracted=RESUME)

    p = store.get_profile_for_ui()
    assert p["name"] == "Arjun", "the résumé renamed the user"
    assert p["location"] == "Mumbai"
    assert p["phone"] == "+91 11111 11111"


def test_it_works_on_the_very_first_upload_too(store):
    """Résumé before profile — the path that already worked, still working."""
    store.update_target_titles_from_resume(["Site Reliability Engineer"], extracted=RESUME)

    p = store.get_profile_for_ui()
    assert p["name"] == "Arjun Mehta"
    assert p["location"] == "Bengaluru"


def test_a_resume_with_nothing_extractable_changes_no_identity(store):
    store.save_profile_from_ui(
        {"name": "Arjun", "email": "arjun@example.com", "target_titles": ["SRE"]})
    store.update_target_titles_from_resume(["SRE"], extracted={})

    p = store.get_profile_for_ui()
    assert p["name"] == "Arjun"
    assert p["location"] == ""


def test_placeholders_never_land_on_an_established_profile(store):
    """"Demo User" exists so a first save passes validation, nothing more."""
    store.save_profile_from_ui(
        {"name": "Arjun", "email": "arjun@example.com", "target_titles": ["SRE"]})
    store.update_target_titles_from_resume(["SRE"], extracted={})

    p = store.get_profile_for_ui()
    assert p["name"] != "Demo User"
    assert p["email"] != "demo@example.com"


def test_titles_still_arrive_with_the_identity(store):
    store.update_target_titles_from_resume(
        ["Site Reliability Engineer", "Platform Engineer"], extracted=RESUME)

    assert store.get_profile_for_ui()["target_titles"] == [
        "Site Reliability Engineer", "Platform Engineer"]
