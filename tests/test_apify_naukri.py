"""Naukri enrichment + opt-in Apify adapter (no live network)."""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))


def test_parse_naukri_listing_keeps_salary_skills_experience():
    from scrapers.naukri_scraper import _parse_naukri_listing

    row = {
        "jobId": "123",
        "title": "Senior Site Reliability Engineer",
        "companyName": "Persistent",
        "jdURL": "https://www.naukri.com/job-123",
        "jobDescription": "Kubernetes, AWS, on-call.",
        "tagsAndSkills": "Kubernetes, AWS, SRE, Python",
        "placeholders": [
            {"type": "experience", "label": "5-10 Yrs"},
            {"type": "salary", "label": "15-25 Lacs PA"},
            {"type": "location", "label": "Bengaluru"},
        ],
        "createdDate": "2 days ago",
    }
    parsed = _parse_naukri_listing(row)
    assert parsed["salary"] == "15-25 Lacs PA"
    assert parsed["location"] == "Bengaluru"
    assert parsed["metadata"]["experience"] == "5-10 Yrs"
    assert "Kubernetes" in parsed["metadata"]["skills"]
    assert parsed["metadata"]["posted_label"] == "2 days ago"


def test_parse_naukri_listing_drops_not_disclosed_salary():
    from scrapers.naukri_scraper import _parse_naukri_listing

    parsed = _parse_naukri_listing(
        {
            "jobId": "1",
            "title": "SRE",
            "companyName": "Acme",
            "jdURL": "https://www.naukri.com/job-1",
            "placeholders": [{"type": "salary", "label": "Not disclosed"}],
        }
    )
    assert parsed["salary"] == ""


def test_naukri_adapter_maps_salary_into_job_record(monkeypatch):
    from models.job import JobRecord
    from sources.adapters import naukri_adapter as mod
    import scrapers.naukri_scraper as scraper

    monkeypatch.setattr(
        scraper,
        "scrape_naukri",
        lambda: [
            {
                "url": "https://www.naukri.com/job-99",
                "company": "Okta",
                "title": "SRE",
                "location": "Bengaluru",
                "jd_snippet": "Okta SRE",
                "salary": "40-60 Lacs PA",
                "notes": "Naukri",
                "metadata": {"skills": ["SRE"], "experience": "8-12 Yrs"},
            }
        ],
    )
    jobs, stats = mod.NaukriAdapter().fetch_raw()
    assert len(jobs) == 1
    assert isinstance(jobs[0], JobRecord)
    assert jobs[0].salary == "40-60 Lacs PA"
    assert jobs[0].metadata["skills"] == ["SRE"]
    assert stats.raw_count == 1


def test_apify_item_to_record_linkedin_shape():
    from sources.adapters.apify_adapter import _item_to_record

    rec = _item_to_record(
        {
            "title": "Site Reliability Engineer",
            "companyName": "UJET",
            "jobUrl": "https://www.linkedin.com/jobs/view/123",
            "location": "Remote",
            "description": "SRE role",
            "salary": "Not disclosed",
        },
        source="LinkedIn",
    )
    assert rec is not None
    assert rec.source == "LinkedIn"
    assert rec.company == "UJET"
    assert rec.salary == ""
    assert rec.url.startswith("https://www.linkedin.com")


def test_apify_item_to_record_naukri_nested_shape():
    """valig/naukri-jobs-scraper returns nested company/salary/experience/description."""
    from sources.adapters.apify_adapter import _item_to_record

    rec = _item_to_record(
        {
            "id": "280726034118",
            "title": "Site Reliability Engineer",
            "url": "https://www.naukri.com/job-listings-site-reliability-engineer-persistent-280726034118",
            "company": {"id": 5929, "name": "Persistent"},
            "salary": {
                "currency": "INR",
                "minimum": 1500000,
                "maximum": 2500000,
                "label": "15-25 Lacs",
            },
            "experience": {"text": "8-11 Yrs", "minimum": "8", "maximum": "11"},
            "locations": [{"label": "Bengaluru"}, {"label": "Pune"}],
            "description": {
                "full": "Strong expertise in Kubernetes<br><br>Hands-on Terraform",
                "short": "Kubernetes|Terraform",
            },
            "skills": {"preferred": ["Kubernetes", "Azure"], "other": ["Terraform"]},
        },
        source="Naukri",
    )
    assert rec is not None
    assert rec.company == "Persistent"
    assert rec.salary == "15-25 Lacs"
    assert "Bengaluru" in rec.location
    assert "Kubernetes" in rec.jd_text
    assert "<br" not in rec.jd_text
    assert rec.metadata["experience"] == "8-11 Yrs"
    assert "Kubernetes" in rec.metadata["skills"]
    assert "Terraform" in rec.metadata["skills"]


def test_apify_adapter_skips_without_token(monkeypatch):
    """No token means no calls at all — not one call per enabled board.

    Patch the *adapter's* binding, not `apify_client`'s. The adapter does
    `from sources.apify_client import get_apify_token` at import time, so it
    holds its own reference and patching the source module leaves it looking
    at the real one. This test passed only because the sandbox blocked the
    network; on a machine with network it made live Apify calls and spent the
    user's credits to assert that it had not.
    """
    import sources.adapters.apify_adapter as adapter

    monkeypatch.setattr(adapter, "get_apify_token", lambda: "")
    jobs, stats = adapter.ApifyAdapter().fetch_raw()
    assert jobs == []
    assert stats.raw_count == 0


def test_apify_run_actor_maps_path(monkeypatch):
    """Actor id user/name becomes user~name; items returned on SUCCEEDED."""
    from sources import apify_client as client

    calls: list[tuple] = []

    class FakeResp:
        def __init__(self, code, payload):
            self.status_code = code
            self._payload = payload
            self.text = str(payload)

        def json(self):
            return self._payload

    def fake_post(url, **kwargs):
        calls.append(("POST", url))
        assert "valig~naukri-jobs-scraper" in url
        return FakeResp(201, {"data": {"id": "run1", "status": "RUNNING"}})

    poll_n = {"n": 0}

    def fake_get(url, **kwargs):
        calls.append(("GET", url))
        if "actor-runs/run1" in url:
            poll_n["n"] += 1
            if poll_n["n"] == 1:
                return FakeResp(200, {"data": {"id": "run1", "status": "RUNNING"}})
            return FakeResp(
                200,
                {"data": {"id": "run1", "status": "SUCCEEDED", "defaultDatasetId": "ds1"}},
            )
        assert "datasets/ds1/items" in url
        return FakeResp(
            200,
            [{"title": "SRE", "company": "Acme", "url": "https://www.naukri.com/x"}],
        )

    monkeypatch.setattr(client.requests, "post", fake_post)
    monkeypatch.setattr(client.requests, "get", fake_get)
    monkeypatch.setattr(client.time, "sleep", lambda *_: None)

    items = client.run_actor(
        "valig/naukri-jobs-scraper",
        {"keywords": "SRE"},
        token="tok",
        timeout_secs=30,
        poll_secs=0,
    )
    assert len(items) == 1
    assert items[0]["title"] == "SRE"


def test_registry_includes_apify():
    from sources.registry import _ADAPTERS

    assert "apify" in _ADAPTERS


def test_bangalore_alias_matches_bengaluru(monkeypatch):
    """Naukri returns Bengaluru; profiles usually say Bangalore."""
    import config as cfg
    from models.job import JobRecord
    from pipeline.filter import passes_title_location

    monkeypatch.setattr(
        cfg,
        "LOCATION_KEYWORDS",
        cfg._expand_location_keywords(["Bangalore", "Remote"]),
    )
    monkeypatch.setattr(
        cfg,
        "SEARCH_KEYWORDS",
        ["Site Reliability Engineer", "SRE"],
    )
    assert "bengaluru" in cfg.LOCATION_KEYWORDS
    job = JobRecord(
        url="https://www.naukri.com/job-1",
        source="Naukri",
        company="Persistent",
        title="Site Reliability Engineer",
        location="Pune, Chennai, Bengaluru",
    )
    assert passes_title_location(job) is True


def test_apify_board_registry_covers_requested_boards():
    from sources.apify_boards import BOARD_REGISTRY, BOARD_SKIPPED, known_board_ids

    for board in (
        "linkedin",
        "naukri",
        "naukrigulf",
        "indeed",
        "dice",
        "seek",
        "upwork",
        "hackernews",
        "glassdoor",
        "ziprecruiter",
    ):
        assert board in BOARD_REGISTRY, board
    assert known_board_ids() == sorted(BOARD_REGISTRY.keys())
    assert "greenhouse" in BOARD_SKIPPED
    assert "workday" in BOARD_SKIPPED
    # Monster is retired, not re-pointed. This entry had already been swapped
    # once (easyapi → bebity) when the first actor 404'd, and bebity now 404s
    # too; every replacement in the store is another paid rental that can vanish
    # the same way. A board that cannot run belongs in BOARD_SKIPPED, where it
    # logs a reason instead of failing a scan and counting toward the circuit
    # breaker.
    assert "monster" not in BOARD_REGISTRY
    assert "monster" in BOARD_SKIPPED


def test_apify_item_to_record_monster_job_posting():
    from sources.adapters.apify_adapter import _item_to_record

    rec = _item_to_record(
        {
            "jobId": "99",
            "jobPosting": {
                "title": "SRE",
                "url": "https://www.monster.com/job-openings/sre-99",
                "description": "On-call Kubernetes",
                "hiringOrganization": {"name": "Acme"},
                "jobLocation": [
                    {
                        "address": {
                            "addressLocality": "Austin",
                            "addressRegion": "TX",
                            "addressCountry": "US",
                        }
                    }
                ],
            },
        },
        source="Monster",
    )
    assert rec is not None
    assert rec.company == "Acme"
    assert rec.title == "SRE"
    assert "Austin" in rec.location
    assert "Kubernetes" in rec.jd_text
