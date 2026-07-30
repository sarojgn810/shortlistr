"""Giving a resume a shape before anything tries to typeset it.

This exists because of a real document. A candidate's tailored resume — one
that went to a referrer — rendered as their name followed by 7,780 characters
of undifferentiated text: no headings, no job entries, and the literal angle
brackets their PDF had wrapped every job title in.

The cause was not the template. A PDF extracts to lines, not structure, so
`parse_cv_markdown` found no `##` headings and dropped the whole document into
`contact`. Every template in the repo renders that identically, because every
template is handed the same shapeless blob.

The cases below are taken from that resume and others like it, so a fix here
is a fix for documents that actually exist rather than for a tidy fixture.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "automation"))

import pytest

from cv.normalize import _heading_for, looks_structured, normalize_cv
from cv.parser import parse_cv_markdown, sections_to_plain_blocks

MESSY = """Ankush Das Barman
9944643636  |  ankush@example.com  |  Linkedin - Ankush Das Barman

Overall Skillset
 Proficient in Mendix (3+ years of relevant Exp)
 Healthy knowledge in SQL (6+ yrs of relevant Exp)

PROFESSIONAL EXPERIENCE (7 Years & 9 months)
<Consultant Technology Solutions>    <ZS Associates Private Limited> <Jan '24 to Present>
 Led 20+ end-to-end RFPs across Commercial and MDM domains, achieving a ~35% win rate and
contributing to
$10M+ pipeline growth.
 Built the Low-Code Practice, increasing project throughput by
2x.
 Delivered client-
aligned proposals across teams.
<Associate Consultant Technology
Solutions>    <ZS Associates> <Jul '22 to Dec'23>
 Played a pivotal role supporting pharmaceutical clients.

Educational Qualification
 B.Tech (Electrical) 2018 VIT University, Vellore 8.35

Extracurricular Activities
 Vice President Education, ZS Toastmasters Club.
"""


@pytest.fixture
def out():
    return normalize_cv(MESSY)


# ── the failure that started this ───────────────────────────────────────────
def test_a_pdf_resume_gets_sections_at_all(out):
    """Before this, every one of these was empty and the whole document sat in
    `contact`. That is what "the resumes aren't good structurally" was."""
    blocks = sections_to_plain_blocks(parse_cv_markdown(out))
    for section in ("skills", "experience", "education"):
        assert blocks[section].strip(), f"{section} is empty"
    assert len(blocks["contact"]) < 200, "the resume must not land in contact"


def test_jobs_become_entries_not_bullets(out):
    """A job with a date range is an entry, so the template can put the role on
    the left and the dates flush right. As bullets they are indistinguishable
    from the achievements underneath them."""
    assert out.count("### ") == 2, out
    assert "### Consultant Technology Solutions ZS Associates Private Limited" in out


def test_angle_brackets_do_not_reach_the_page(out):
    """Some exporters wrap every field in "<...>". They rendered, visibly, in
    the PDF that went to a referrer."""
    assert "<" not in out and ">" not in out


def test_a_bracket_broken_across_a_line_break_is_still_removed(out):
    """"<Associate Consultant Technology\\nSolutions>" left a stray "<" opening
    a bullet and a stray ">" opening the next job's title — so one job appeared
    twice, wrongly, in the rendered resume."""
    assert "### Associate Consultant Technology Solutions ZS Associates" in out


# ── lines a page break split ────────────────────────────────────────────────
def test_a_sentence_split_by_the_page_is_put_back(out):
    """A PDF has no paragraphs, only lines at whatever width the page was.
    Bulleting each one gave a bullet reading "$10M+ pipeline growth."."""
    assert "contributing to $10M+ pipeline growth." in out
    assert "\n- $10M+" not in out


def test_a_continuation_starting_with_a_digit_is_rejoined(out):
    """"increasing project throughput by\\n2x." left "2x." as its own bullet."""
    assert "throughput by 2x." in out
    assert "\n- 2x." not in out


def test_a_hyphen_at_a_line_break_is_kept(out):
    """"client-\\naligned" is the real compound "client-aligned" far more often
    than a broken "clientaligned" — which is the word an earlier version of
    this produced in somebody's resume."""
    assert "client-aligned" in out
    assert "clientaligned" not in out


# ── headings as people actually write them ──────────────────────────────────
@pytest.mark.parametrize("line,expect", [
    ("PROFESSIONAL EXPERIENCE (7 Years & 9 months)", "Experience"),
    ("Overall Skillset", "Skills"),
    ("Educational Qualification", "Education"),      # singular
    ("Educational Qualifications", "Education"),     # plural
    ("Extracurricular Activities", "Additional"),
    ("Key Projects", "Projects"),
    ("CORE COMPETENCIES", "Skills"),
    ("Certifications", "Certifications"),
])
def test_headings_are_recognised_however_they_are_written(line, expect):
    assert _heading_for(line) == expect


def test_a_sentence_mentioning_experience_is_not_a_heading():
    """A heading is short and on its own line. Without the length guard, any
    sentence containing the word would start a new section mid-job."""
    assert _heading_for(
        "Nine years of experience delivering low-code platforms at scale") == ""


def test_a_section_with_no_home_is_kept_rather_than_swallowed(out):
    """"Extracurricular Activities" has no canonical section, and without one
    it was appended as three more bullets on the previous job."""
    assert "## Additional" in out
    assert "Toastmasters" in out.split("## Additional")[1]


# ── it does not damage a resume that is already good ────────────────────────
def test_a_structured_resume_is_left_alone():
    """Re-imposing structure on a document that has it is how a good resume
    gets flattened."""
    good = ("# Asha R\n\n**asha@example.com**\n\n## Summary\n\nBackend engineer.\n\n"
            "## Experience\n\n### Senior Engineer — Acme\n*2019 – 2024*\n\n- Built things.\n")
    assert looks_structured(good)
    assert "## Summary" in normalize_cv(good)
    assert "Backend engineer." in normalize_cv(good)


def test_nothing_is_ever_lost():
    """The one hard rule. A resume is a factual claim about somebody's life,
    and a normaliser that drops a job is worse than one that files it untidily.
    """
    for text in (MESSY, "just one line", "", "   "):
        # Heading lines are excluded: "Overall Skillset" becoming "## Skills"
        # is the point of the exercise, not a loss. Everything else must survive.
        body = [l for l in text.splitlines() if not _heading_for(l)]
        src_words = {w for w in " ".join(body).split()
                     if len(w) > 4 and w.isalpha()}
        got = normalize_cv(text)
        missing = {w for w in src_words if w not in got}
        assert not missing, f"lost: {sorted(missing)[:5]}"


def test_an_unsegmentable_document_is_returned_unchanged():
    """Better the original than an empty skeleton with a name on it."""
    blob = "qqq zzz\nwww vvv\n"
    assert "qqq" in normalize_cv(blob)
