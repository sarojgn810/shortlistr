"""The résumé template catalogue.

Every template is single-column LaTeX built on the shared preamble in
``cv/latex_layout.py``: same ATS hardening, same page-break discipline, same
alignment primitives. A template file contains only the parts that differ —
colour, section rules, header arrangement, section order.

Display names are Shortlistr-branded. Layout ideas adapted from well-known
open-source ATS templates (Jake's Resume / sb2nov, Awesome-CV, Reactive-Resume,
latexcv) — rebuilt as single-column skins that share our pipeline.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from config import SHORTLISTR_ROOT

TEMPLATES_DIR = os.path.join(SHORTLISTR_ROOT, "templates", "cv-latex")

# Highlighted in the Resume UI as the strongest default picks.
_RECOMMENDED = frozenset({"ats-single", "professional", "tech-compact", "harvard-ats"})


@dataclass(frozen=True)
class CvTemplate:
    id: str
    name: str
    description: str
    ats_notes: str
    filename: str
    family: str = "classic"
    # Heading overrides, keyed by the canonical section name.
    section_titles: dict[str, str] = field(default_factory=dict)
    # How well the design tolerates being squeezed. A layout that separates
    # sections with whitespace alone stops reading as separate sections once
    # the fit search takes that whitespace away, so it is not pushed as far.
    max_density: str = "tight"
    inspiration: str = ""


CV_TEMPLATES: tuple[CvTemplate, ...] = (
    CvTemplate(
        "ats-single",
        "Shortlistr Classic",
        "Black on white, hairline rules, dates flush right. The Jake's / "
        "sb2nov single-column shape recruiters expect — our reference design.",
        "Greenhouse, Lever, Workday, Ashby",
        "ats-single.tex",
        "ats",
        inspiration="Jake's Resume · sb2nov/resume (MIT)",
    ),
    CvTemplate(
        "professional",
        "Shortlistr Professional",
        "One navy accent, thin rules, nothing shouting. The everyday pick when "
        "you want polish without decoration.",
        "Safe everywhere",
        "professional.tex",
        inspiration="Clean ATS professional layouts",
    ),
    CvTemplate(
        "tech-compact",
        "Shortlistr Compact",
        "Sans-serif, name and contact on one line, tuned to hold a long career "
        "on a single page — dense without looking cramped.",
        "Safe — densest of the set",
        "tech-compact.tex",
        inspiration="Jake's Resume density (MIT)",
    ),
    CvTemplate(
        "harvard-ats",
        "Shortlistr Campus",
        "Centred header, unruled bold headings, no colour. The shape university "
        "career offices teach — safest for older enterprise parsers.",
        "Safest for older enterprise parsers",
        "harvard-ats.tex",
        inspiration="University career-office ATS style",
    ),
    CvTemplate(
        "awesome-inspired",
        "Shortlistr Crimson",
        "Crimson name and section titles, each heading trailed by a rule to "
        "the margin. Adapted from Awesome-CV, rebuilt single-column for ATS.",
        "Safe — the original filled header band was dropped for parsers",
        "awesome-inspired.tex",
        "awesome",
        {"summary": "Professional Summary", "skills": "Core Competencies",
         "experience": "Professional Experience"},
        inspiration="posquit0/Awesome-CV (LPPL) — layout idea only",
    ),
    CvTemplate(
        "reactive-modern",
        "Shortlistr Teal",
        "Sans-serif with a teal stripe beside each section title. Look adapted "
        "from Reactive-Resume, kept single-column and parser-safe.",
        "Safe — the stripe is a drawn rule, not an image",
        "reactive-modern.tex",
        "reactive",
        inspiration="AmruthPillai/Reactive-Resume (MIT)",
    ),
    CvTemplate(
        "classic-ats",
        "Shortlistr Serif",
        "Centred name, full-width rules, serif body. Traditional recruiter "
        "shape — ten-thousand-times-familiar.",
        "Safe everywhere",
        "classic-ats.tex",
        inspiration="Traditional ATS serif layouts",
    ),
    CvTemplate(
        "executive",
        "Shortlistr Executive",
        "Slate blue, heavy rules, summary given the most weight on the page. "
        "For senior / staff / leadership applications.",
        "Safe — headings renamed only to other standard strings",
        "executive.tex",
        section_titles={"summary": "Executive Summary", "skills": "Core Competencies"},
        inspiration="Executive ATS formats",
    ),
    CvTemplate(
        "skills-first",
        "Shortlistr Skills",
        "The keyword block sits above the summary — for scanners and humans "
        "filtering on a stack rather than a story.",
        "Safe — good for keyword-weighted screens",
        "skills-first.tex",
        section_titles={"skills": "Technical Skills"},
        inspiration="Skills-forward ATS layouts",
    ),
    CvTemplate(
        "modern-minimal",
        "Shortlistr Air",
        "No rules at all; whitespace separates the sections. Needs room to "
        "breathe, so it is squeezed less hard than the others.",
        "Safe — headings stay bold and standard",
        "modern-minimal.tex",
        max_density="snug",
        inspiration="Minimal ATS whitespace layouts",
    ),
    CvTemplate(
        "latexcv-sidebar",
        "Shortlistr Split",
        "Name left, contact right, body full width. Inspired by latexcv's "
        "sidebar idea — columns stay in the header so body text stays linear.",
        "Safe — a real sidebar interleaves into the body text",
        "latexcv-sidebar.tex",
        "sidebar",
        inspiration="jankapunkt/latexcv (sidebar idea)",
    ),
    CvTemplate(
        "minimal-plain",
        "Shortlistr Plain",
        "Black on white, no rules, no accent. The fallback when a parser has "
        "surprised you — maximum parse reliability.",
        "Maximum parse reliability",
        "minimal-plain.tex",
        inspiration="Bare ATS plaintext layouts",
    ),
)


def list_templates() -> list[dict]:
    return [
        {
            "id": t.id,
            "name": t.name,
            "description": t.description,
            "ats_notes": t.ats_notes,
            "family": t.family,
            "recommended": t.id in _RECOMMENDED,
            "inspiration": t.inspiration,
        }
        for t in CV_TEMPLATES
    ]


def get_template(template_id: str) -> CvTemplate | None:
    for t in CV_TEMPLATES:
        if t.id == template_id:
            return t
    return None


def template_path(template_id: str) -> str:
    t = get_template(template_id)
    if not t:
        raise ValueError(f"Unknown template: {template_id}")
    path = os.path.join(TEMPLATES_DIR, t.filename)
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    return path


def template_family(template_id: str) -> str:
    t = get_template(template_id)
    return t.family if t else "classic"
