"""A PDF has lines on a page, not words and paragraphs.

Reported as "the templates are not giving us the correct output". The templates
were innocent — they rendered cv.md faithfully, and cv.md said:

    Bangalore,India•+918884311573•realsarojnayak@gmail.com
    Feb2024–Present
    ... and Agentic AI —
    building LLM-powered autonomous incident response ...

Checked against raw pdfplumber output, which is identical before and after the
letter-spacing repair, so this is not a reader bug either. A typeset résumé
positions glyphs rather than writing space characters, and wraps sentences to
fit a column. Extraction reports what is in the file.

Both are corrected where the fix is unambiguous, and nowhere else: a decimal, a
URL, a thousands separator, a heading and a list item all have to survive
untouched, because a résumé that is subtly rewritten is worse than one that
reads slightly tight.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "automation"))

from cv.ingest import normalize_spacing, rejoin_wrapped_lines


# ── putting separators back ──────────────────────────────────────────────────

def test_a_contact_row_gets_its_spaces():
    assert normalize_spacing("Bangalore,India•+91900•a@b.com") == (
        "Bangalore, India • +91900 • a@b.com")


def test_a_month_is_separated_from_its_year():
    assert normalize_spacing("Feb2024–Present") == "Feb 2024–Present"
    assert normalize_spacing("Jan2023–Dec2023") == "Jan 2023–Dec 2023"


def test_decimals_are_left_alone():
    assert normalize_spacing("from 2.3% to 0.8%") == "from 2.3% to 0.8%"


def test_a_thousands_separator_is_left_alone():
    assert normalize_spacing("1,200 requests") == "1,200 requests"


def test_a_url_is_left_alone():
    assert normalize_spacing("linkedin.com/in/name") == "linkedin.com/in/name"


def test_something_that_only_looks_like_a_month_is_left_alone():
    assert normalize_spacing("COVID19 and H2024") == "COVID19 and H2024"


def test_an_already_spaced_list_is_unchanged():
    assert normalize_spacing("Python, Bash, Java") == "Python, Bash, Java"


def test_a_bullet_starting_a_line_keeps_its_line():
    """The first version used \\s*, which ate the newline and folded a whole
    list onto one line."""
    src = "Wipro Bangalore\n• AIOps Platform: X\n• LLM Runbook: Y"
    assert len(normalize_spacing(src).split("\n")) == 3


# ── undoing the page's line wrapping ─────────────────────────────────────────

def test_a_sentence_wrapped_by_the_layout_is_rejoined():
    assert rejoin_wrapped_lines("and Agentic AI —\nbuilding LLM systems.") == (
        "and Agentic AI — building LLM systems.")


def test_a_finished_sentence_is_not_joined_to_the_next():
    src = "Deployed it.\nNext sentence here."
    assert rejoin_wrapped_lines(src) == src


def test_a_capitalised_line_starts_something_new():
    src = "Site Reliability Engineer\nWipro Bangalore, India"
    assert rejoin_wrapped_lines(src) == src


def test_headings_are_never_absorbed():
    src = "# SAROJ NAYAK\nsome following text"
    assert rejoin_wrapped_lines(src) == src


def test_list_items_stay_separate():
    src = "- AIOps Platform: X\n- LLM Runbook: Y"
    assert rejoin_wrapped_lines(src) == src


def test_a_line_after_a_list_item_is_not_pulled_into_it():
    """Ambiguous, so left alone — a wrong join rewrites the résumé."""
    src = "- AIOps Platform: architected a thing\nreducing noise by 55%."
    assert rejoin_wrapped_lines(src) == src


def test_blank_lines_survive():
    assert rejoin_wrapped_lines("Para one\n\nPara two").count("\n") == 2


def test_empty_input_is_not_an_error():
    assert rejoin_wrapped_lines("") == ""
    assert normalize_spacing("") == ""
