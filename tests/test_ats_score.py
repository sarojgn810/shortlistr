"""ATS scoring accuracy tests."""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))

SAMPLE_CV = """# Jane Doe

**SF** | **jane@example.com**

## PROFESSIONAL SUMMARY

SRE with 5 years and 40% MTTR reduction on Kubernetes platforms.

## CORE COMPETENCIES

Kubernetes, Terraform, Prometheus, Python

## PROFESSIONAL EXPERIENCE

### SRE | Acme | 2020 – Present

- Cut incidents 30% with SLO-driven alerting.

## EDUCATION

B.S. CS | State U | 2015 – 2019

## CERTIFICATIONS

- AWS CCP
"""


def test_name_inferred_when_title_is_resume():
    from cv.ats_score import score_ats_readiness

    md = """# Resume

**Alex Candidate**
Seattle | alex@example.com

## PROFESSIONAL SUMMARY

Platform engineer with 9 years experience and 40% incident reduction.

## CORE COMPETENCIES

Kubernetes, Terraform, AWS, Python

## PROFESSIONAL EXPERIENCE

### SRE | Acme | 2020 – Present
- Reduced MTTR by 35%

## EDUCATION

B.Tech | IIT | 2015
"""
    r = score_ats_readiness(md, include_template=False)
    name = next(c for c in r["checks"] if c["label"] == "Name")
    assert name["ok"] is True
    assert r["score"] >= 80


def test_pdf_style_bullets_count():
    from cv.ats_score import score_ats_readiness

    md = """# Alex Dev

alex@example.com

## PROFESSIONAL SUMMARY

DevOps lead with 8 years and 50% faster deploys.

## CORE COMPETENCIES

Docker, K8s, CI/CD, Linux

## PROFESSIONAL EXPERIENCE

Engineer | Corp | 2018
•Cut costs 20%
•Owned on-call rotation

## EDUCATION

BS IT | 2016
"""
    r = score_ats_readiness(md, include_template=False)
    exp = next(c for c in r["checks"] if c["label"] == "Work experience")
    assert exp["ok"] is True


def test_fix_hints_are_actionable():
    from cv.ats_score import score_ats_readiness

    r = score_ats_readiness("# Hi\n\nno sections", include_template=False)
    for fix in r["fixes"]:
        assert "Add or improve" not in fix["hint"].lower()
        assert len(fix["hint"]) > 10
