"""hiring.cafe — sitemaps they publish, structured data they publish.

Their robots.txt allows /job, /jobs and /recently-posted-jobs, advertises five
sitemaps, and disallows /viewjob/, /org/, /company/ and /cdn-cgi/. Their
/api/search-jobs answers 401, so it is private and left alone even though it
would be the convenient thing to call.

Dice was requested at the same time and is not here. Its robots.txt disallows
/job, /jobsearch/, /jobs?q*, /jobs/?q* and both /feed/ and /rss/ — every path a
posting lives on. There is no permitted way in, which is the same conclusion
Jobsora got.

Slug filtering is the point of the design: the sitemap holds 22,200 postings
across every trade there is, 231 of which matched an SRE profile on the first
live run. Fetching a page per posting to discard 98% of them would be slow and
rude, so the slug decides before anything is fetched.
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "automation"))

from scrapers.hiringcafe_scraper import (
    _company,
    _job_posting_from_html,
    _location,
    _sitemap_locs,
    _slug_matches,
)

KEYWORDS = ["Site Reliability Engineer", "SRE", "DevOps Engineer", "MLOps Engineer"]


# ── reading the sitemap ──────────────────────────────────────────────────────

def test_locs_are_pulled_from_a_sitemap():
    xml = ("<urlset><url><loc>https://hiringcafe.com/job/a-1</loc></url>"
           "<url><loc>  https://hiringcafe.com/job/b-2  </loc></url></urlset>")
    assert _sitemap_locs(xml) == ["https://hiringcafe.com/job/a-1",
                                  "https://hiringcafe.com/job/b-2"]


def test_an_empty_sitemap_is_not_an_error():
    assert _sitemap_locs("") == []
    assert _sitemap_locs("<urlset></urlset>") == []


# ── deciding before fetching ─────────────────────────────────────────────────

def test_a_matching_slug_is_selected():
    for url in ("https://hiringcafe.com/job/senior-site-reliability-engineer-acme-abc123",
                "https://hiringcafe.com/job/devops-engineer-remote-xyz789",
                "https://hiringcafe.com/job/mlops-engineer-paris-doctolib-4f4f"):
        assert _slug_matches(url, KEYWORDS), url


def test_an_unrelated_slug_is_skipped_without_a_fetch():
    """The sitemap is mostly policing, nursing and driving roles."""
    for url in ("https://hiringcafe.com/job/police-officer-lateral-certified-6fd8",
                "https://hiringcafe.com/job/registered-nurse-icu-nights-0bd3",
                "https://hiringcafe.com/job/cdl-a-truck-driver-regional-yn8a"):
        assert not _slug_matches(url, KEYWORDS), url


def test_no_keywords_matches_nothing():
    """An empty profile must not pull the whole board."""
    assert not _slug_matches("https://hiringcafe.com/job/site-reliability-engineer-x", [])


# ── reading the posting ──────────────────────────────────────────────────────

def _page(*blocks: dict) -> str:
    return "".join(
        f'<script type="application/ld+json">{json.dumps(b)}</script>' for b in blocks
    )


def test_the_job_posting_block_is_found():
    html = _page({"@type": "JobPosting", "title": "Senior SRE"})
    assert _job_posting_from_html(html)["title"] == "Senior SRE"


def test_the_posting_is_found_among_other_blocks():
    """Pages carry breadcrumbs and organisation blocks; the first is not it."""
    html = _page(
        {"@type": "BreadcrumbList", "itemListElement": []},
        {"@type": "Organization", "name": "Acme"},
        {"@type": "JobPosting", "title": "DevOps Engineer"},
    )
    assert _job_posting_from_html(html)["title"] == "DevOps Engineer"


def test_a_posting_nested_in_a_graph_is_found():
    html = _page({"@context": "https://schema.org",
                  "@graph": [{"@type": "WebSite"},
                             {"@type": "JobPosting", "title": "MLOps Engineer"}]})
    assert _job_posting_from_html(html)["title"] == "MLOps Engineer"


def test_a_page_with_no_posting_yields_none():
    assert _job_posting_from_html(_page({"@type": "Organization"})) is None
    assert _job_posting_from_html("<html><body>nothing</body></html>") is None


def test_malformed_json_does_not_raise():
    """A broken block on one page must not end the scan."""
    assert _job_posting_from_html('<script type="application/ld+json">{oops</script>') is None


# ── the fields ───────────────────────────────────────────────────────────────

def test_company_comes_from_the_hiring_organisation():
    assert _company({"hiringOrganization": {"name": "Doctolib"}}) == "Doctolib"
    assert _company({"hiringOrganization": "Hearst"}) == "Hearst"
    assert _company({}) == ""


def test_location_is_assembled_from_the_address():
    node = {"jobLocation": {"address": {"addressLocality": "Paris",
                                        "addressRegion": "Île-de-France",
                                        "addressCountry": "FR"}}}
    assert _location(node) == "Paris, Île-de-France, FR"


def test_a_list_of_locations_takes_the_first():
    node = {"jobLocation": [{"address": {"addressLocality": "Pune"}},
                            {"address": {"addressLocality": "Delhi"}}]}
    assert _location(node) == "Pune"


def test_a_remote_posting_says_remote():
    assert _location({"jobLocationType": "TELECOMMUTE"}) == "Remote"


def test_a_posting_with_no_location_is_blank_not_wrong():
    assert _location({}) == ""


# ── the adapter ──────────────────────────────────────────────────────────────

def test_the_adapter_is_registered_and_on_by_default():
    from sources.registry import get_registry

    assert "hiringcafe" in get_registry().enabled


def test_a_failing_board_does_not_end_the_scan(monkeypatch):
    from sources.adapters.hiringcafe_adapter import HiringCafeAdapter

    def boom(*a, **k):
        raise RuntimeError("hiring.cafe is down")

    monkeypatch.setattr("sources.adapters.hiringcafe_adapter.fetch_jobs", boom)
    jobs, stats = HiringCafeAdapter().fetch_raw()
    assert jobs == []
    assert "down" in (stats.error or "")
