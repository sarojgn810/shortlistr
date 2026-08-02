"""Template registry and preview layout tests."""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))


def test_every_template_is_registered_and_present():
    from cv.templates import CV_TEMPLATES, list_templates

    assert len(CV_TEMPLATES) == 12
    ids = {t["id"] for t in list_templates()}
    assert "awesome-inspired" in ids
    assert "latexcv-sidebar" in ids
    assert "reactive-modern" in ids


def test_all_template_tex_files_exist():
    from cv.templates import CV_TEMPLATES, template_path

    for t in CV_TEMPLATES:
        assert os.path.isfile(template_path(t.id)), t.id
        raw = open(template_path(t.id), encoding="utf-8").read()
        # Every template is a skin over the shared preamble. A template that
        # still carries its own documentclass is the shape that used to
        # diverge: different ligature rules, missing \entry, silent compile
        # failures.
        assert "{{PREAMBLE}}" in raw, t.id
        assert "{{PROJECTS}}" in raw and "{{ADDITIONAL}}" in raw, t.id


def test_every_template_gets_the_shared_ats_preamble():
    from cv.latex_builder import build_latex
    from cv.templates import CV_TEMPLATES

    md = "# Asha\n\n## Summary\nShort.\n\n## Skills\nPython\n\n## Experience\n### Eng 2020 – Present\n- Did things.\n"
    for t in CV_TEMPLATES:
        tex = build_latex(md, t.id)
        assert r"\entry{" in tex, t.id
        assert "Ligatures      = NoCommon" in tex or r"\DisableLigatures" in tex, t.id
        assert "{{PREAMBLE}}" not in tex, t.id
        assert r"\cvsection{Experience}" in tex or r"\cvsection{Professional Experience}" in tex, t.id


def test_sample_cv_uses_demo_candidate():
    from cv.preview import SAMPLE_CV, render_cv_html

    assert "Alex Candidate" in SAMPLE_CV
    html = render_cv_html("", template_id="awesome-inspired")
    assert "Alex Candidate" in html
    assert "c0392b" in html or "layout-awesome" in html


def test_sidebar_layout_renders():
    from cv.preview import render_cv_html

    html = render_cv_html("", template_id="latexcv-sidebar")
    # Header split only — a real sidebar column is ATS-hostile and was dropped.
    assert "cv-header-split" in html
    assert 'class="cv-sidebar"' not in html
    assert "Alex Candidate" in html


def test_reactive_layout_renders():
    from cv.preview import render_cv_html

    html = render_cv_html("", template_id="reactive-modern")
    assert "cv-accent-bar" in html
