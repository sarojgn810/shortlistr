"""The résumé template catalogue.

Every template is single-column LaTeX built on the shared preamble in
``cv/latex_layout.py``: same ATS hardening, same page-break discipline, same
alignment primitives. A template file contains only the parts that differ —
colour, section rules, header arrangement, section order.

``section_titles`` lets a design rename a heading, but only to another string
an ATS recognises as standard. "Executive Summary" is safe; "Career History"
is not, and is the kind of flourish that costs a keyword match.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from config import SHORTLISTR_ROOT

TEMPLATES_DIR = os.path.join(SHORTLISTR_ROOT, "templates", "cv-latex")


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


CV_TEMPLATES: tuple[CvTemplate, ...] = (
    CvTemplate(
        "ats-single",
        "ATS Single Column",
        "Black on white, hairline rules, dates flush right. The reference "
        "design — every other template here is this one with a skin.",
        "Greenhouse, Lever, Workday, Ashby",
        "ats-single.tex",
        "ats",
    ),
    CvTemplate(
        "professional",
        "Professional",
        "One navy accent, thin rules, nothing shouting. The general-purpose "
        "pick when you have no reason to choose anything else.",
        "Safe everywhere",
        "professional.tex",
    ),
    CvTemplate(
        "awesome-inspired",
        "Awesome CV",
        "Crimson name and section titles, each heading trailed by a rule to "
        "the margin. Layout idea from posquit0/Awesome-CV, rebuilt single-column.",
        "Safe — the original's filled header band was dropped for parsers",
        "awesome-inspired.tex",
        "awesome",
        {"summary": "Professional Summary", "skills": "Core Competencies",
         "experience": "Professional Experience"},
    ),
    CvTemplate(
        "reactive-modern",
        "Reactive Modern",
        "Sans-serif with a teal stripe beside each section title. Look adapted "
        "from AmruthPillai/Reactive-Resume.",
        "Safe — the stripe is a drawn rule, not an image",
        "reactive-modern.tex",
        "reactive",
    ),
    CvTemplate(
        "classic-ats",
        "Classic ATS",
        "Centred name, full-width rules, serif body. The shape a recruiter has "
        "seen ten thousand times.",
        "Safe everywhere",
        "classic-ats.tex",
    ),
    CvTemplate(
        "tech-compact",
        "Tech Compact",
        "Sans-serif, name and contact sharing one line, tuned to hold a long "
        "career to a single page.",
        "Safe — densest of the set",
        "tech-compact.tex",
    ),
    CvTemplate(
        "modern-minimal",
        "Modern Minimal",
        "No rules at all; whitespace separates the sections. Needs room to "
        "breathe, so it is squeezed less hard than the others.",
        "Safe — headings stay bold and standard",
        "modern-minimal.tex",
        max_density="snug",
    ),
    CvTemplate(
        "executive",
        "Executive",
        "Slate blue, heavy rules, the summary given the most weight on the page.",
        "Safe — headings renamed only to other standard strings",
        "executive.tex",
        section_titles={"summary": "Executive Summary", "skills": "Core Competencies"},
    ),
    CvTemplate(
        "skills-first",
        "Skills First",
        "The keyword block sits above the summary, for scanners and humans "
        "filtering on a stack rather than a story.",
        "Safe — good for keyword-weighted screens",
        "skills-first.tex",
        section_titles={"skills": "Technical Skills"},
    ),
    CvTemplate(
        "harvard-ats",
        "Harvard ATS",
        "Centred header, unruled bold headings, no colour anywhere. The shape "
        "university career offices teach.",
        "Safest for older enterprise parsers",
        "harvard-ats.tex",
    ),
    CvTemplate(
        "latexcv-sidebar",
        "Split Header",
        "Name left, contact right, body full width. Was a true sidebar; the "
        "two columns are now confined to the header, where they cost nothing.",
        "Safe — a real sidebar interleaves into the body text",
        "latexcv-sidebar.tex",
        "sidebar",
    ),
    CvTemplate(
        "minimal-plain",
        "Minimal Plain",
        "Black on white, no rules, no accent. The fallback for a parser that "
        "has surprised you.",
        "Maximum parse reliability",
        "minimal-plain.tex",
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
