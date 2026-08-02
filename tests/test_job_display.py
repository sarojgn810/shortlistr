"""Deterministic structuring of Gmail / Naukri title blobs."""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))

from processors.job_display import apply_structure_to_job, structure_from_blob


def test_gmail_sre_cisco_blob():
    raw = (
        "site reliability engineer sre cloud platform golang docker "
        "cisco bengaluru 6 to 11 years 300726500660"
    )
    got = structure_from_blob(title=raw)
    assert "Site Reliability Engineer" in got["title"] or got["title"].startswith(
        "Site Reliability"
    )
    assert "300726500660" not in got["title"]
    assert got["company"].lower() == "cisco"
    assert "Bengaluru" in got["location"]
    assert "6" in got["experience"] and "11" in got["experience"]


def test_title_at_company_pattern():
    got = structure_from_blob(title="Staff Platform Engineer at Stripe – Remote")
    assert "Platform Engineer" in got["title"] or "Staff" in got["title"]
    assert "Stripe" in got["company"]
    assert "Remote" in got["location"]


def test_preserves_explicit_company_and_location():
    got = structure_from_blob(
        title="Senior SRE",
        company="Datadog",
        location="Dublin",
        experience="5+ years",
    )
    assert got["title"] == "Senior SRE" or "SRE" in got["title"]
    assert got["company"] == "Datadog"
    assert "Dublin" in got["location"]
    assert "5" in got["experience"]


def test_apply_structure_fills_missing_only():
    job = {
        "title": (
            "devops engineer docker kubernetes acme bangalore 4 to 8 years 9988776655"
        ),
        "company": "Unknown",
        "location": "",
        "experience": "",
    }
    out = apply_structure_to_job(job)
    assert out["company"] and out["company"].lower() != "unknown"
    assert "Acme" in out["company"]
    assert "Bengaluru" in out["location"] or "Bangalore" in out["location"]
    assert out["experience"]
    assert "9988776655" not in out["title"]


def test_apply_structure_keeps_short_clean_title():
    job = {
        "title": "Backend Engineer",
        "company": "Acme",
        "location": "Pune",
        "experience": "3–5 years",
    }
    out = apply_structure_to_job(job)
    assert out["title"] == "Backend Engineer"
    assert out["company"] == "Acme"
    assert out["location"] == "Pune"


def test_rejects_digit_and_salary_company():
    from processors.job_display import is_plausible_company

    assert not is_plausible_company("1659474")
    assert not is_plausible_company("3 ₹6L")
    assert not is_plausible_company(".A Complex ₹2L")
    assert is_plausible_company("Cisco")


def test_apply_structure_clears_junk_company():
    job = {
        "title": "Site Reliability Engineer Bengaluru",
        "company": "1659474",
        "location": "",
        "experience": "",
    }
    out = apply_structure_to_job(job)
    assert out["company"] in ("", None) or not str(out["company"]).isdigit()
    assert "Bengaluru" in (out.get("location") or "")


def test_strips_salary_from_title_blob():
    got = structure_from_blob(title="Lead SRE ₹3L Bengaluru")
    assert "₹" not in got["title"]
    assert "3L" not in got["title"].replace(" ", "")
    assert "Bengaluru" in got["location"]

