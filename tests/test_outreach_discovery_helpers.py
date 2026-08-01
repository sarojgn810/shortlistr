"""Unit tests for TrySideDoor-style discovery / outreach helpers."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "automation"))

from models.job import JobRecord  # noqa: E402
from models.soft_dedupe import collapse_soft_duplicates, soft_key  # noqa: E402
from sources.ats_fingerprint import fingerprint_url  # noqa: E402
from contacts.email_find import permute_emails, company_domain_guess  # noqa: E402
from export.instantly_csv import rows_from_contacts, to_csv  # noqa: E402


def test_fingerprint_greenhouse_and_smartrecruiters():
    gh = fingerprint_url("https://job-boards.greenhouse.io/acme")
    assert gh and gh["ats_type"] == "greenhouse" and gh["token"] == "acme"
    sr = fingerprint_url("https://careers.smartrecruiters.com/Freshworks")
    assert sr and sr["ats_type"] == "smartrecruiters" and sr["token"] == "Freshworks"
    rt = fingerprint_url("https://doctolib.recruitee.com/")
    assert rt and rt["ats_type"] == "recruitee" and rt["token"] == "doctolib"
    wd = fingerprint_url("https://redhat.wd5.myworkdayjobs.com/jobs")
    assert wd and wd["ats_type"] == "workday" and wd["tenant"] == "redhat"


def test_soft_dedupe_prefers_richer_jd():
    a = JobRecord(
        url="https://boards.greenhouse.io/x/jobs/1",
        source="Greenhouse",
        company="Acme",
        title="SRE",
        location="Bengaluru",
        jd_text="short",
        job_id="a",
    )
    b = JobRecord(
        url="https://www.linkedin.com/jobs/view/2",
        source="LinkedIn",
        company="Acme",
        title="SRE",
        location="Bengaluru",
        jd_text="much longer job description with requirements and stack details here",
        job_id="b",
    )
    assert soft_key("Acme", "SRE", "Bengaluru")
    out = collapse_soft_duplicates([a, b])
    assert len(out) == 1
    assert "longer job description" in (out[0].jd_text or "")
    assert "linkedin.com" in (out[0].url or "")


def test_permute_emails_and_instantly_csv():
    assert company_domain_guess("Stripe", "https://www.stripe.com/careers") == "stripe.com"
    emails = permute_emails("Jane Doe", "acme.com")
    assert "jane.doe@acme.com" in emails
    rows = rows_from_contacts(
        [{"name": "Jane Doe", "email": "jane.doe@acme.com", "linkedin_url": "https://linkedin.com/in/jane"}],
        company="Acme",
        personalization="Saw the SRE role",
    )
    csv = to_csv(rows)
    assert "email,first_name,last_name,company_name" in csv
    assert "jane.doe@acme.com" in csv
    assert "Jane" in csv and "Doe" in csv
