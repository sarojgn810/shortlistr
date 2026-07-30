"""HTML resume preview."""

from __future__ import annotations

from cv.preview import render_cv_html

SAMPLE = """# Pat Lee

**email@example.com**

## PROFESSIONAL SUMMARY

Engineer with 5 years experience.

## CORE COMPETENCIES

Python, Go

## PROFESSIONAL EXPERIENCE

### DevOps | Co | 2020 – Present

- Improved deploy time 50%.

## EDUCATION

BS CS

## CERTIFICATIONS

- CKA
"""


def test_render_cv_html_includes_name():
    html = render_cv_html(SAMPLE, "classic-ats")
    assert "Pat Lee" in html
    assert "Professional Summary" in html
    assert "a4-sheet" in html
    assert "fitOnePage" in html


def test_render_all_extra_sections():
    md = SAMPLE + "\n\n## PROJECTS\n\n- Built CI/CD pipeline."
    html = render_cv_html(md, "classic-ats")
    assert "Projects" in html
    assert "CI/CD" in html


def test_skips_empty_sections():
    md = """# Only Name

**email@test.com**

## PROFESSIONAL SUMMARY

Short summary here.
"""
    html = render_cv_html(md, "classic-ats")
    assert "Certifications" not in html
    assert "Short summary" in html


def test_skills_first_template_order():
    html = render_cv_html(SAMPLE, "skills-first")
    skills_pos = html.find("Core Competencies")
    summary_pos = html.find("Professional Summary")
    assert skills_pos < summary_pos
