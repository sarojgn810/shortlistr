"""Gmail verify-before-publish gate."""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))

from processors.gmail_verify import (
    UNVERIFIED,
    VERIFIED,
    prepare_gmail_records,
    verify_gmail_job,
)
from models.job import JobRecord


def test_non_gmail_defaults_confirmed():
    out = verify_gmail_job(
        {
            "source": "greenhouse",
            "title": "SRE",
            "company": "Acme",
            "url": "https://example.com/jobs/1",
            "jd_text": "",
        }
    )
    assert out["metadata"]["verification"] == VERIFIED


def test_gmail_without_jd_is_unverified():
    with (
        patch("scrapers.ats_url_resolver.resolve_job_url", return_value=None),
        patch("processors.enrich_jd.enrich_job_page", return_value={"ok": False}),
    ):
        out = verify_gmail_job(
            {
                "source": "gmail",
                "title": (
                    "site reliability engineer sre cloud platform golang docker "
                    "cisco bengaluru 6 to 11 years 300726500660"
                ),
                "company": "",
                "url": "https://www.naukri.com/job-listings-xyz",
                "jd_text": "",
            }
        )
    assert out["metadata"]["verification"] == UNVERIFIED
    assert out["company"].lower() == "cisco"
    assert "Bengaluru" in out["location"]
    assert out["metadata"].get("verify_keywords")


def test_gmail_confirmed_when_jd_fetched():
    long_jd = "x" * 250
    with patch(
        "scrapers.ats_url_resolver.resolve_job_url",
        return_value={
            "title": "Site Reliability Engineer",
            "company": "Cisco",
            "location": "Bengaluru",
            "jd_text": long_jd,
            "salary": "",
        },
    ):
        out = verify_gmail_job(
            {
                "source": "gmail",
                "title": "sre cisco bengaluru 6 to 11 years 300726500660",
                "company": "",
                "url": "https://boards.greenhouse.io/cisco/jobs/1",
                "jd_text": "",
            }
        )
    assert out["metadata"]["verification"] == VERIFIED
    assert len(out["jd_text"]) >= 200
    assert "Cisco" in out["company"]


def test_prepare_gmail_records_tags_metadata():
    job = JobRecord(
        url="https://www.naukri.com/job-listings-abc",
        source="gmail",
        company="",
        title="mlops engineer aws hyderabad 5 to 9 years 1122334455",
        location="",
        jd_text="",
        metadata={},
    )
    with (
        patch("scrapers.ats_url_resolver.resolve_job_url", return_value=None),
        patch("processors.enrich_jd.enrich_job_page", return_value={"ok": False}),
    ):
        out = prepare_gmail_records([job])
    assert len(out) == 1
    assert out[0].metadata.get("verification") == UNVERIFIED
    assert "Hyderabad" in (out[0].location or "")
