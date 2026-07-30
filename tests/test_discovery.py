"""Tests for hybrid job discovery (ATS URL resolver + search parsing)."""

from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUTOMATION = os.path.join(ROOT, "automation")
sys.path.insert(0, AUTOMATION)


@pytest.mark.parametrize(
    "url,ats_type,slug,job_id",
    [
        (
            "https://job-boards.greenhouse.io/vercel/jobs/1234567890",
            "greenhouse",
            "vercel",
            "1234567890",
        ),
        (
            "https://boards-api.greenhouse.io/v1/boards/datadog/jobs/999",
            "greenhouse",
            "datadog",
            "999",
        ),
        (
            "https://jobs.lever.co/retool/a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "lever",
            "retool",
            "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        ),
        (
            "https://jobs.ashbyhq.com/linear/550e8400-e29b-41d4-a716-446655440000",
            "ashby",
            "linear",
            "550e8400-e29b-41d4-a716-446655440000",
        ),
    ],
)
def test_parse_ats_url(url, ats_type, slug, job_id):
    from scrapers.ats_url_resolver import parse_ats_url

    parsed = parse_ats_url(url)
    assert parsed is not None
    assert parsed.ats_type == ats_type
    assert parsed.slug == slug
    assert parsed.job_id == job_id


def test_parse_ats_url_rejects_non_ats():
    from scrapers.ats_url_resolver import is_ats_job_url, parse_ats_url

    assert parse_ats_url("https://www.linkedin.com/jobs/view/123") is None
    assert not is_ats_job_url("https://example.com/careers")


def test_extract_ats_urls_from_text():
    from processors.search_discovery import extract_ats_urls

    text = (
        "See https://job-boards.greenhouse.io/acme/jobs/42 and "
        "https://jobs.lever.co/foo/a1b2c3d4-e5f6-7890-abcd-ef1234567890"
    )
    urls = extract_ats_urls(text)
    assert len(urls) == 2
    assert "greenhouse.io/acme/jobs/42" in urls[0]


def test_discover_from_search_empty_without_portals(tmp_path, monkeypatch):
    from processors import search_discovery

    monkeypatch.setattr(search_discovery, "_auto_location_queries", lambda: [])
    missing = tmp_path / "no-portals.yml"
    offers, stats = search_discovery.discover_from_search(portals_path=str(missing))
    assert offers == []
    assert stats["queries_run"] == 0


def test_resolve_job_url_mock_greenhouse(monkeypatch):
    from scrapers import ats_url_resolver

    class FakeResp:
        status_code = 200

        def json(self):
            return {
                "id": 42,
                "title": "Senior DevOps Engineer",
                "absolute_url": "https://job-boards.greenhouse.io/acme/jobs/42",
                "location": {"name": "Remote"},
                "content": "<p>Build infra</p>",
                "departments": [{"name": "Engineering"}],
            }

    monkeypatch.setattr(ats_url_resolver.requests, "get", lambda *a, **k: FakeResp())

    job = ats_url_resolver.resolve_job_url(
        "https://job-boards.greenhouse.io/acme/jobs/42"
    )
    assert job is not None
    assert job["title"] == "Senior DevOps Engineer"
    assert job["source"] == "Greenhouse"


def test_himalayas_uses_profile_queries():
    from scrapers.himalayas_scraper import _aggregator_queries

    queries = _aggregator_queries(max_queries=4)
    assert len(queries) >= 1
    assert all(len(q) >= 3 for q in queries)


def test_datadog_careers_html_resolve(monkeypatch):
    from scrapers import ats_url_resolver

    html = (
        "<html><head><title>Manager II, Engineering - SRE | Datadog Careers</title></head></html>"
    )

    class FakeResp:
        status_code = 200
        url = "https://careers.datadoghq.com/detail/7947006/"

        @property
        def text(self):
            return html

    monkeypatch.setattr(ats_url_resolver.requests, "get", lambda *a, **k: FakeResp())
    job = ats_url_resolver.resolve_job_url("https://careers.datadoghq.com/detail/7947006/")
    assert job is not None
    assert job["company"] == "Datadog"
    assert "SRE" in job["title"]


def test_can_resolve_careers_hosts():
    from scrapers.ats_url_resolver import can_resolve_job_url

    assert can_resolve_job_url("https://careers.datadoghq.com/detail/123/")
    assert can_resolve_job_url("https://www.kentik.com/careers/jobs/456/")
    assert not can_resolve_job_url("https://example.com/jobs/1")
