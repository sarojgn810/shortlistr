"""Job card scoring display + résumé skill tokenization."""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))


def test_skill_signals_are_atomic_tokens(tmp_path, monkeypatch):
    cv = tmp_path / "cv.md"
    cv.write_text(
        "# Ada\n\n## PROFESSIONAL SUMMARY\nSRE on Kubernetes.\n\n"
        "## TECHNICAL SKILLS\n"
        "SRE & Reliability SLO / SLI / Error Budgets, Incident & On-Call Management\n"
        "Cloud & Platforms AWS, Kubernetes, Docker, Helm, Prometheus, Grafana, Terraform\n",
        encoding="utf-8",
    )
    import config
    import processors.job_filter as jf

    monkeypatch.setattr(config, "CV_MD_PATH", str(cv))
    # job_filter imports CV_MD_PATH inside the function from config — patch module attr
    skills = jf.skill_signals()
    assert "kubernetes" in skills
    assert "aws" in skills
    assert "prometheus" in skills
    assert "terraform" in skills
    # Category blobs must not be the only signals
    assert not any("&" in s for s in skills)


def test_empty_jd_does_not_blame_resume(tmp_path, monkeypatch):
    cv = tmp_path / "cv.md"
    cv.write_text(
        "# Ada\n\n## TECHNICAL SKILLS\nKubernetes, AWS, Prometheus, Terraform, Python\n\n"
        "## PROFESSIONAL SUMMARY\nSite Reliability Engineer.\n",
        encoding="utf-8",
    )
    import config
    import processors.job_filter as jf

    monkeypatch.setattr(config, "CV_MD_PATH", str(cv))
    monkeypatch.setattr(config, "SEARCH_KEYWORDS", ["site reliability engineer", "sre"])
    monkeypatch.setattr(config, "LOCATION_KEYWORDS", ["bengaluru", "bangalore", "india"])
    monkeypatch.setattr(config, "REMOTE_STRICT", False)
    monkeypatch.setattr(config, "MIN_SALARY_INR_LPA", 0)
    monkeypatch.setattr(config, "MIN_SALARY_USD", 0)
    monkeypatch.setattr(config, "SALARY_UNLISTED", "include")
    monkeypatch.setattr(config, "DEAL_BREAKERS", [])
    monkeypatch.setattr(config, "CANDIDATE", {"years_exp": 9})

    thin = jf.score_job(
        {
            "title": "Site Reliability Engineer",
            "location": "Bengaluru East, Karnataka, India",
            "jd_snippet": "",
            "description": "",
        }
    )
    assert thin["fit_score"] >= 50
    assert "no résumé skills" not in thin["fit_reason"]
    assert "JD not fetched yet" in thin["fit_reason"]
    # "title match" once, not twice
    assert thin["fit_reason"].count("title match") == 1

    rich = jf.score_job(
        {
            "title": "Site Reliability Engineer",
            "location": "Bengaluru East, Karnataka, India",
            "jd_snippet": (
                "Operate kubernetes on AWS with prometheus, grafana, terraform and python. "
                "Own incident response and SLOs."
            ),
            "description": "",
        }
    )
    # A real JD that overlaps the résumé must score at least as well as a blank JD
    assert rich["fit_score"] >= thin["fit_score"]
    assert "JD skills:" in rich["fit_reason"]
    assert rich["fit_score"] <= 100


def test_display_score_maps_discovery_over_twenty():
    """Mirror the JobCard mapping (fit/20) so discovery never reads as >5/5."""
    fit_score = 60  # title + provisional + location — the Infosys pending card
    shown = min(5, fit_score / 20)
    assert shown == 3.0
    assert min(5, 100 / 20) == 5.0
