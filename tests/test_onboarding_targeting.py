"""What a fresh clone gets out of onboarding decides what it ever finds.

A second clone of this repo, same CV, same portals.yml, produced
`location: AWS` and five target titles. Discovery still read ~11,000 postings a
scan; the title filter threw away almost everything, so Discover looked empty
and it read as "jobs are not being fetched".

Two causes, both here rather than in discovery:

  * "AWS" satisfied every location rule. It is short, alphabetic, carries no
    digits and is not a role word, so it was accepted as the candidate's home
    city and then seeded preferred_locations.
  * Only titles[0] was expanded through _title_aliases. Titles two onwards were
    taken verbatim, so the profile searched roughly the words already printed on
    the résumé.
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))


# ── a technology is not a place ──────────────────────────────────────────────

def test_tech_acronyms_are_not_read_as_a_home_city():
    from cv.profile_extract import _single_token_location

    for token in ("AWS", "GCP", "SQL", "API", "K8S", "CI"):
        assert not _single_token_location(token), f"{token} accepted as a location"


def test_real_single_word_cities_still_pass():
    from cv.profile_extract import _single_token_location

    for town in ("Bangalore", "London", "Pune", "Bhubaneswar", "Chennai"):
        assert _single_token_location(town), f"{town} rejected"


def test_longer_technology_names_are_not_read_as_a_home_city():
    """Three letters was never the boundary — a technology of any length is one.

    The first pass at this rejected all-caps tokens up to six characters, which
    left every longer or title-case skills entry accepted: "Terraform" came out
    of _extract_location as the candidate's city.
    """
    from cv.profile_extract import _single_token_location

    for token in ("TERRAFORM", "KUBERNETES", "JENKINS", "GRAFANA",
                  "Terraform", "Kubernetes", "Python",
                  "AWS GCP Azure", "Kubernetes Terraform Python", "CI/CD"):
        assert not _single_token_location(token), f"{token} accepted as a location"


def test_an_all_caps_contact_row_still_yields_its_city():
    """Uppercase is not evidence of a technology.

    PUNE and DUBAI are four and five characters and are set in caps whenever the
    contact row is, so rejecting short all-caps tokens wholesale loses the city
    outright — and an unseeded preferred_locations turns the discovery location
    filter off entirely.
    """
    from cv.profile_extract import _single_token_location, extract_profile_fields

    for town in ("PUNE", "DELHI", "MUMBAI", "LONDON", "DUBAI", "BERLIN"):
        assert _single_token_location(town), f"{town} rejected"

    md = (
        "# RAHUL SHARMA\n"
        "PUNE | rahul@example.com | +91 90000 00000\n\n"
        "## Experience\n"
        "### Site Reliability Engineer\n"
        "Acme, 2020-2024.\n"
    )
    out = extract_profile_fields(md)
    assert out.get("location") == "PUNE", out
    assert out.get("preferred_locations") == ["PUNE"], out


def test_country_codes_survive_the_length_floor():
    """"UK" is two characters and a real answer."""
    from cv.profile_extract import _single_token_location

    for code in ("UK", "USA", "UAE"):
        assert _single_token_location(code), f"{code} rejected"


def test_a_skills_row_cannot_seed_preferred_locations():
    """The end-to-end version: a CV whose contact row is followed by skills."""
    from cv.profile_extract import extract_profile_fields

    md = (
        "# Priya Rao\n"
        "Bangalore, India | priya@example.com | +91 90000 00000\n\n"
        "## Skills\n"
        "AWS, Kubernetes, Terraform\n\n"
        "## Experience\n"
        "### Site Reliability Engineer\n"
        "Acme, 2020-2024. Ran the platform.\n"
    )
    out = extract_profile_fields(md)
    assert "AWS" not in str(out.get("location", ""))
    assert "AWS" not in str(out.get("preferred_locations", ""))


# ── every title gets expanded, not only the first ────────────────────────────

def test_titles_after_the_first_are_expanded_too():
    from cv.profile_extract import extract_profile_fields

    md = (
        "# Sam Doe\n"
        "Pune, India | sam@example.com\n\n"
        "## Experience\n"
        "### Site Reliability Engineer\n"
        "Acme, 2021-2024.\n"
        "### DevOps Engineer\n"
        "Globex, 2018-2021.\n"
    )
    titles = extract_profile_fields(md).get("target_titles") or []
    low = [t.lower() for t in titles]

    # The second role's own family has to be represented, not just its literal
    # string — expanding titles[0] alone is the bug this file exists for.
    assert any("platform engineer" in t for t in low), titles
    assert any("infrastructure engineer" in t for t in low), titles


def test_an_sre_resume_reaches_the_adjacent_roles():
    """A CV lists jobs held. Targeting should cover jobs obtainable."""
    from cv.profile_extract import _title_aliases

    aliases = [a.lower() for a in _title_aliases("Site Reliability Engineer")]
    for neighbour in ("platform engineer", "infrastructure engineer",
                      "devops engineer", "cloud engineer"):
        assert any(neighbour in a for a in aliases), f"{neighbour} missing from {aliases}"


def test_the_title_picks_its_family_not_the_dict_order():
    """"MLOps Platform Engineer" is an MLOps role that happens to say platform.

    The trigger list is a dict, and matching it in insertion order meant
    "platform engineer" won over "mlops" purely because it is written earlier
    in the literal — so an ML profile was targeted at SRE and infrastructure and
    reached no ML posting at all. The qualifier a title leads with decides.
    """
    from cv.profile_extract import _title_aliases

    ml = [a.lower() for a in _title_aliases("MLOps Platform Engineer")]
    assert "mlops engineer" in ml, ml
    assert "machine learning engineer" in ml, ml

    # And the reverse reading still holds where the title really does lead with
    # the generic role.
    plat = [a.lower() for a in _title_aliases("Platform Engineer (DevOps)")]
    assert "site reliability engineer" in plat, plat


def test_a_caps_heading_is_not_a_second_target_title():
    """PDF extraction shouts; "DEVOPS ENGINEER" and "DevOps Engineer" are one.

    Deduplication compared exact strings, so a résumé with caps headings put
    both spellings in the profile — visible as duplicates in onboarding, and
    spending slots against the cap that adjacent roles should have had.
    """
    from cv.profile_extract import extract_profile_fields

    md = (
        "# SAM DOE\n"
        "Pune, India | sam@example.com\n\n"
        "## EXPERIENCE\n"
        "### DEVOPS ENGINEER\n"
        "Acme, 2021-2024.\n"
        "### SITE RELIABILITY ENGINEER\n"
        "Globex, 2018-2021.\n"
    )
    titles = extract_profile_fields(md)["target_titles"]
    assert len({t.lower() for t in titles}) == len(titles), titles
    # The canonical spelling is the one that survives, not the shouted one.
    assert "DevOps Engineer" in titles, titles
    assert "Site Reliability Engineer" in titles, titles


def test_expansion_stays_bounded():
    """Wider targeting is the point; an unbounded list is not."""
    from cv.profile_extract import extract_profile_fields

    md = "# A B\nPune, India | a@b.com\n\n## Experience\n" + "".join(
        f"### {role}\nCo {2000+i}-{2001+i}.\n" for i, role in enumerate([
            "Site Reliability Engineer", "DevOps Engineer", "Platform Engineer",
            "Infrastructure Engineer", "Cloud Engineer", "MLOps Engineer",
            "AIOps Engineer", "Data Engineer", "Backend Engineer",
        ]))
    titles = extract_profile_fields(md).get("target_titles") or []
    assert len(titles) <= 16, f"{len(titles)} titles is a filter that filters nothing"
    assert len(set(t.lower() for t in titles)) == len(titles), "duplicates in the list"
