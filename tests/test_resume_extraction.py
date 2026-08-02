"""Reading a one-page, two-column, letter-spaced résumé.

A designer-style CV was uploaded and onboarding picked up no email, no LinkedIn
URL and no target titles. None of the patterns were at fault — the text never
arrived in a readable state. pypdf renders letter-spaced headings one glyph at a
time, so the page came out as:

    M a n o j N a y a k L i v e @ g m a i l . c o m
    S e n i o r  D a t a  E n g i n e e r

126 of 136 lines looked like that. Three separate defects followed from it, and
two more were hiding behind it:

1. pypdf is the wrong reader for this. pdfplumber places glyphs by position and
   returns ordinary words; it is tried first now.
2. Letter-spacing repair still runs on whatever the reader returns, because the
   fallback reader needs it.
3. Two-column layouts merge the sidebar into the body ("## SKILLS WORK
   EXPERIENCE"), so no experience section is recognised and title extraction had
   nothing to work with. The headline under the name is the fallback.
4. A location needed a comma, so a bare "Bengaluru" was dropped.
5. Contact rows put phone, link, city and email on one line with no separators.
   Splitting on "/" offered "in" — from linkedin.com/in/name — as the city.

All fixtures here are invented. Real résumés belong nowhere near this repo.
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))

from cv.ingest import _is_letter_spaced, _unspace_line, repair_letter_spacing
from cv.profile_extract import (
    _location_from_contact_row,
    _single_token_location,
    extract_profile_fields,
)


# ── putting letter-spaced text back together ─────────────────────────────────

def test_a_letter_spaced_line_is_detected():
    assert _is_letter_spaced("S e n i o r  D a t a  E n g i n e e r")


def test_ordinary_prose_is_left_alone():
    for line in ("Senior Data Engineer with 6+ years of experience",
                 "Mumbai, Maharashtra",
                 "- Built ELT pipelines on Snowflake using dbt and SQL"):
        assert not _is_letter_spaced(line), line


def test_a_short_line_is_never_treated_as_spaced():
    """"A B C" is an initialism, not a mangled word."""
    assert not _is_letter_spaced("A B C")


def test_words_are_rebuilt_from_the_wider_gaps():
    """One space sits between letters, two or more between words."""
    assert _unspace_line("J a n e  D o e") == "Jane Doe"
    assert _unspace_line("S e n i o r  D a t a  E n g i n e e r") == "Senior Data Engineer"


def test_an_email_survives_the_rebuild():
    assert _unspace_line("j a n e d o e @ e x a m p l e . c o m") == "janedoe@example.com"


def test_a_url_survives_the_rebuild():
    got = _unspace_line("l i n k e d i n . c o m / i n / j a n e d o e")
    assert got == "linkedin.com/in/janedoe"


def test_a_markdown_marker_keeps_its_space():
    """"# a b c" must not collapse into "#abc" and stop being a heading."""
    assert _unspace_line("# J a n e  D o e") == "# Jane Doe"


def test_repair_only_touches_the_damaged_lines():
    text = "\n".join([
        "# J a n e  D o e",
        "Senior Data Engineer with 6+ years of experience",
        "j a n e d o e @ e x a m p l e . c o m",
    ])
    assert repair_letter_spacing(text).split("\n") == [
        "# Jane Doe",
        "Senior Data Engineer with 6+ years of experience",
        "janedoe@example.com",
    ]


def test_repair_of_empty_text_is_empty():
    assert repair_letter_spacing("") == ""


# ── the city on a one-line contact row ───────────────────────────────────────

def test_the_city_is_recovered_from_a_contact_row():
    row = "98765 43210 linkedin.com/in/janedoe Bengaluru janedoe@example.com"
    assert _location_from_contact_row(row) == "Bengaluru"


def test_a_url_fragment_is_not_a_city():
    """The "in" in linkedin.com/in/name was being offered as the location."""
    assert not _single_token_location("in")
    assert not _single_token_location("com")
    assert not _single_token_location("linkedin")


def test_a_bare_city_is_accepted():
    """The old rule required a comma, so "Bengaluru" alone was dropped."""
    for value in ("Bengaluru", "Remote", "San Francisco"):
        assert _single_token_location(value), value


def test_a_job_title_is_not_a_city():
    assert not _single_token_location("Senior Data Engineer")


def test_a_row_with_no_city_yields_nothing():
    assert _location_from_contact_row("98765 43210 janedoe@example.com") == ""


# ── the whole résumé ─────────────────────────────────────────────────────────

RESUME = """\
# Jane Doe
Senior Data Engineer
Senior Data Engineer with 6+ years of experience building ELT pipelines
on modern cloud data platforms.
98765 43210 linkedin.com/in/janedoe Bengaluru janedoe@example.com

## SKILLS WORK EXPERIENCE
Data Engineering: Northwind
ELT Pipeline Design Senior Data Engineer
"""


def test_every_onboarding_field_is_recovered():
    """The four the user reported missing, plus what they seed."""
    fields = extract_profile_fields(RESUME)
    assert fields.get("email") == "janedoe@example.com"
    assert fields.get("linkedin") == "https://linkedin.com/in/janedoe"
    assert fields.get("location") == "Bengaluru"
    assert "Senior Data Engineer" in (fields.get("target_titles") or [])


def test_the_headline_supplies_the_title_when_sections_merge():
    """A two-column layout gives "## SKILLS WORK EXPERIENCE" and no experience
    section at all, so nothing else can name the role."""
    fields = extract_profile_fields(RESUME)
    titles = fields.get("target_titles") or []
    assert titles and titles[0] == "Senior Data Engineer"


def test_the_home_city_seeds_targeting():
    assert extract_profile_fields(RESUME).get("preferred_locations") == ["Bengaluru"]


def test_an_empty_resume_extracts_nothing_and_does_not_raise():
    assert extract_profile_fields("") == {}
