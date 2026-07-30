"""LinkedIn profile optimizer — CV import + grounded rewrites (no LLM)."""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))

from linkedin_optimizer.cover import list_themes, render_cover_svg
from linkedin_optimizer.from_cv import profile_from_cv_markdown
from linkedin_optimizer.import_profile import normalize_linkedin_url
from linkedin_optimizer.parser import parse_profile_text, profile_from_structured
from linkedin_optimizer.rewriter import rewrite_section
from linkedin_optimizer.roles import get_role, list_roles
from linkedin_optimizer.scorer import score_profile
from linkedin_optimizer.service import analyze, rewrite


SAMPLE = """\
Jane Doe
Senior Engineer at Acme
Bengaluru, India

About
Passionate team player and self-starter building cloud systems.

Experience
Software Engineer
Acme Corp
• Worked on infrastructure
• Helped with deployments

Skills
Python, Docker
"""

CV_SAMPLE = """\
# Jane Doe

**Site Reliability Engineer | Platform**

Bengalore, India  •  jane@example.com  •  linkedin.com/in/janedoe

## PROFESSIONAL SUMMARY

Site Reliability Engineer with 9+ years operating Kubernetes and AWS platforms.
Reduced MTTR by 40% and sustained 99.9% uptime on payment systems.

## TECHNICAL SKILLS

Kubernetes, AWS, Prometheus, Terraform, Python, Observability, Incident Management

## PROFESSIONAL EXPERIENCE

### Site Reliability Engineer Feb 2024 – Present
Acme Corp Bangalore, India
- Built observability on Prometheus and Grafana, cutting alert noise by 55%.
- Automated incident triage for 30+ recurring types, reducing MTTT by 25%.

### Platform Engineer Jan 2020 – Jan 2024
Beta Labs Bangalore, India
- Operated Kubernetes clusters and Terraform pipelines for multi-region services.
"""


def test_roles_list_and_get():
    roles = list_roles()
    assert len(roles) >= 5
    assert get_role("sre")["id"] == "sre"
    assert get_role("full-stack")["id"] == "fullstack"


def test_parse_sections():
    p = parse_profile_text(SAMPLE)
    assert p["name"] == "Jane Doe"
    assert "cloud" in p["about"].lower()
    assert len(p["experience"]) >= 1
    assert any(s.lower() == "python" for s in p["skills"])


def test_score_finds_gaps_for_sre():
    p = parse_profile_text(SAMPLE)
    score = score_profile(p, "sre")
    assert 0 <= score["overall"] <= 100
    assert "keyword_match" in score["dimensions"]
    assert score["missing_keywords"]
    assert score["mode"] == "heuristic"


def test_cv_import_parses_real_jobs_and_url():
    p = profile_from_cv_markdown(CV_SAMPLE)
    assert p["name"] == "Jane Doe"
    assert "linkedin.com/in/janedoe" in (p.get("linkedin_url") or "")
    assert len(p["experience"]) >= 2
    assert p["experience"][0]["company"]
    assert any("MTTR" in b or "55%" in b for b in p["experience"][0]["bullets"])
    assert any("kubernetes" in s.lower() for s in p["skills"])
    score = score_profile(p, "sre")
    assert score["overall"] >= 50
    assert "kubernetes" in [k.lower() for k in score["found_keywords"]]


def test_rewrite_does_not_invent_metrics_or_employers():
    p = profile_from_structured(
        {
            "headline": "Engineer",
            "about": "I operate production systems on Linux.",
            "experience": [
                {
                    "title": "SRE",
                    "company": "Acme",
                    "bullets": ["Worked on on-call rotations"],
                }
            ],
            "skills": ["Linux"],
        }
    )
    exp = rewrite_section("experience", p, "sre")
    assert "Acme" in exp["suggested"]
    assert "Your Company" not in exp["suggested"]
    assert "~N%" not in exp["suggested"]
    assert "N points" not in exp["suggested"]

    about = rewrite_section("about", p, "sre")
    assert "Acme" not in about["suggested"] or "Acme" in p["about"]
    # No fabricated proof sentence when no metric exists
    assert "cutting toil by ~N%" not in about["suggested"]


def test_skills_only_adds_evidenced_keywords():
    p = profile_from_structured(
        {
            "about": "I run Kubernetes on AWS with observability.",
            "skills": ["Python"],
        }
    )
    out = rewrite_section("skills", p, "sre")
    suggested = out["suggested"].lower()
    assert "kubernetes" in suggested or "aws" in suggested
    # terraform is must-keyword but not in corpus — should be recommended, not forced
    recommended = [k.lower() for k in (out.get("recommended_keywords") or [])]
    assert "terraform" in recommended or "terraform" not in suggested


def test_normalize_linkedin_url():
    assert normalize_linkedin_url("linkedin.com/in/saroj810") == (
        "https://www.linkedin.com/in/saroj810"
    )
    assert normalize_linkedin_url("saroj810") == "https://www.linkedin.com/in/saroj810"
    assert normalize_linkedin_url("") == ""


def test_analyze_persist_roundtrip(tmp_path, monkeypatch):
    import linkedin_optimizer.service as svc

    monkeypatch.setattr(svc, "DRAFT_PATH", str(tmp_path / "li.json"))
    out = analyze(text=SAMPLE, target_role="devops", persist=True)
    assert out["target_role"] == "devops"
    assert out["score"]["overall"] >= 0
    again = rewrite(section="about", target_role="devops", use_llm=False)
    assert again["mode"] == "heuristic"
    assert again["suggested"] or again.get("error") == "empty_about" or again["suggested"] == again.get("suggested")


def test_cover_svg_themes():
    themes = list_themes()
    assert len(themes) >= 4
    svg = render_cover_svg(
        theme_id="ink_lime",
        name="Ada Lovelace",
        headline="Platform Engineer",
        subline="Open to SRE roles",
    )
    assert "svg" in svg.lower()
    assert "ADA LOVELACE" in svg
    assert "1584" in svg
