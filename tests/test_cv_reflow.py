"""Hard-wrapped source markdown has to render as whole sentences.

A `cv.md` produced by ingesting a PDF is wrapped at the *visual* line, roughly
130 characters. Both renderers used to treat one source line as one paragraph,
so a two-line bullet became a one-item list plus an orphan paragraph sitting
outside it at zero indent. Seven bullets in a job became seven lists and seven
orphans; the résumé ran to four pages and looked like a text dump.

These tests pin the joining rules, because the failure was invisible in the
source (the markdown was fine) and only showed up in the rendered PDF.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "automation"))

from cv.latex_builder import _md_to_latex_body, _split_when
from cv.reflow import join_wrapped, parse_blocks

WRAPPED_JOB = """### Site Reliability Engineer Feb 2024 – Present
Wipro Bangalore, India
- AIOps Platform: Architected AI-driven alert correlation across a Splunk and New Relic observability stack, reducing alert noise
by 55% and dramatically improving on-call signal-to-noise ratio.
- SLO Engineering: Designed an SLO/SLI/error-budget framework for a payment gateway processing $2B+ in daily transactions,
sustaining a 99.9% uptime SLA across all production environments.
"""


def _blocks(text: str):
    return parse_blocks(text, split_when=_split_when)


def test_a_bullet_split_across_two_lines_is_one_bullet():
    blocks = _blocks(WRAPPED_JOB)
    bullets = [b for b in blocks if b.kind == "bullets"]
    assert len(bullets) == 1, "each wrapped bullet used to open its own list"
    assert len(bullets[0].items) == 2
    assert bullets[0].items[0].endswith("on-call signal-to-noise ratio.")
    assert "reducing alert noise by 55%" in bullets[0].items[0]


def test_the_line_under_a_role_is_the_employer_not_body_text():
    kinds = [b.kind for b in _blocks(WRAPPED_JOB)]
    assert kinds[:3] == ["entry", "meta", "bullets"]


def test_wrapped_prose_becomes_one_paragraph():
    text = (
        "Site Reliability Engineer with 9+ years designing, scaling, and operating "
        "mission-critical, high-availability distributed\n"
        "systems for Fortune 500 enterprises. Deep expertise across SRE, DevOps, AIOps, "
        "MLOps, and Agentic AI while building\n"
        "LLM-powered autonomous incident response and predictive anomaly detection."
    )
    blocks = _blocks(text)
    assert len(blocks) == 1 and blocks[0].kind == "para"
    assert "distributed systems for Fortune 500" in blocks[0].text


def test_short_lines_stay_separate_items():
    """Certifications and degrees are a list of lines, not wrapped prose.
    Joining them would run three qualifications into one sentence."""
    text = "AWS Certified Solutions Architect\nITIL Foundation\nCKA"
    assert [b.text for b in _blocks(text)] == [
        "AWS Certified Solutions Architect", "ITIL Foundation", "CKA"
    ]


def test_a_hyphen_at_the_wrap_point_keeps_its_compound():
    """This class of extractor breaks at spaces, never mid-syllable, so a
    trailing hyphen belongs to the word. Joining on a space printed
    "cloud- native" and "Cross- functional"."""
    assert join_wrapped("self-healing infrastructure on cloud-", "native Kubernetes") == (
        "self-healing infrastructure on cloud-native Kubernetes"
    )
    assert join_wrapped("40% MTTR reduction,", "and toil elimination") == (
        "40% MTTR reduction, and toil elimination"
    )


def test_a_degree_line_ending_in_dates_gets_the_flush_right_column():
    """Education and Projects come out of a PDF without `###` headings. As
    prose they lose the date column that Experience has, and the two sections
    stop looking like the same document."""
    text = "B.Tech — Electronics Engineering, Krupajal Engineering College, India 2007 – 2011"
    (block,) = _blocks(text)
    assert block.kind == "entry"
    assert block.when == "2007 – 2011"
    assert block.text.endswith("India")


def test_a_long_paragraph_that_happens_to_end_in_dates_stays_prose():
    text = (
        "Site Reliability Engineer who has run payment-grade platforms through every "
        "peak season since the team was founded, holding a 99.9% uptime SLA "
        "throughout the period 2019 – 2024"
    )
    (block,) = _blocks(text)
    assert block.kind == "para"


def test_the_latex_body_emits_one_itemize_for_the_whole_list():
    tex = _md_to_latex_body(WRAPPED_JOB)
    assert tex.count(r"\begin{itemize}") == 1
    assert tex.count(r"\item ") == 2
    assert r"\entrymeta{Wipro Bangalore, India}" in tex
    # The orphan continuation used to land here as a bare paragraph.
    assert r"\par" not in tex


def test_two_degrees_in_a_row_are_two_entries():
    """The second degree is not the first one's institution.

    The PhD is hard-wrapped over two source lines, so it is only recognised as
    an entry once the pair is joined — at which point the *next* line was taken
    for the subtitle that follows a role heading. The rendered Education section
    showed one bold degree with "B.Tech — Electronics Engineering, Krupajal
    Engineering College" set underneath it in the small italic used for
    employers, reading as the school that awarded the PhD.
    """
    text = (
        "Executive PhD — Artificial Intelligence & Machine Learning (Pursuing), "
        "National Institute of Technology (NIT) Rourkela,\n"
        "India 2026 – Present\n"
        "B.Tech — Electronics Engineering, Krupajal Engineering College, "
        "Bhubaneswar, India 2007 – 2011"
    )
    blocks = _blocks(text)
    assert [b.kind for b in blocks] == ["entry", "entry"]
    assert [b.when for b in blocks] == ["2026 – Present", "2007 – 2011"]
    assert blocks[0].text.startswith("Executive PhD")
    assert blocks[1].text.startswith("B.Tech")


def test_a_subtitle_without_dates_is_still_a_subtitle():
    """The guard above must not cost Projects and Experience their meta line."""
    text = (
        "Enterprise RAG Chat Engine — Capstone Project 2025 – Present\n"
        "Personal / Self-Directed Bangalore, India"
    )
    blocks = _blocks(text)
    assert [b.kind for b in blocks] == ["entry", "meta"]
    assert blocks[1].text == "Personal / Self-Directed Bangalore, India"


def test_a_skills_category_is_emphasised():
    """"Cloud & Platforms: AWS, Kubernetes" — the category has to stand out or
    the section is an undifferentiated wall of comma-separated nouns."""
    tex = _md_to_latex_body("Cloud & Platforms: AWS (EC2, EKS), Kubernetes, Docker")
    assert tex.startswith(r"\textbf{Cloud \& Platforms:}")
    assert "Kubernetes" in tex


def test_prose_containing_a_colon_mid_sentence_is_not_relabelled():
    """A summary is not a skills row; bolding a fragment of it would be wrong."""
    text = (
        "Site Reliability Engineer with 9+ years designing and operating "
        "mission-critical platforms. Deep expertise across SRE and DevOps: "
        "the through-line is reliability."
    )
    tex = _md_to_latex_body(text)
    assert r"\textbf" not in tex
