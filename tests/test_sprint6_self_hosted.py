"""Placeholder CV + eval mode tests."""

from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))

PLACEHOLDER = """# Your Name

**email@example.com**

## PROFESSIONAL SUMMARY

Your role, years of experience, core stack, and one measurable win.
"""

REAL_CV = """# Alex Candidate

**Remote** | **alex@example.com**

## PROFESSIONAL SUMMARY

Software Engineer with 5 years on distributed systems. Cut MTTR 40%.

## CORE COMPETENCIES

Python, Kubernetes

## PROFESSIONAL EXPERIENCE

### Software Engineer | Acme | 2020 – Present

- Reduced incidents 30%.

## EDUCATION

B.S. Computer Science

## CERTIFICATIONS

- AWS Solutions Architect
"""


def test_is_placeholder_cv():
    from cv.placeholder import is_placeholder_cv

    assert is_placeholder_cv(PLACEHOLDER) is True
    assert is_placeholder_cv(REAL_CV) is False


def test_heuristic_eval_sets_template_mode():
    from eval.service import evaluate_job_text

    result = evaluate_job_text(
        "We need Kubernetes and Terraform SRE remote",
        url="https://boards.greenhouse.io/acme/jobs/1",
        company="acme",
        role="SRE",
    )
    d = result.to_dict()
    assert d["eval_mode"] == "template"
    assert d["template_only"] is True
    for key in "ABCDEFG":
        assert key in d["blocks"] and d["blocks"][key]
    assert d["legitimacy"] == "likely"


def test_prep_cover_draft_roundtrip(monkeypatch, tmp_path):
    import config
    import store.db as db_mod
    from store.prep_drafts import get_cover_letter_draft, save_cover_letter_draft

    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(db_mod, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(db_mod, "DB_PATH", str(tmp_path / "shortlistr.db"))

    save_cover_letter_draft("abc123", "Dear hiring manager,\n\nHello.")
    assert "Dear hiring manager" in get_cover_letter_draft("abc123")
