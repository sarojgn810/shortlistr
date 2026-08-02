"""Free LinkedIn guest discovery stays profile-driven and scrape-only."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "automation"))


@pytest.fixture(autouse=True)
def isolated_cache(monkeypatch, tmp_path):
    """Point the HTTP cache at a temp dir for every test in this file.

    Guest search reads the disk cache before it sends anything, so without this
    each test would both serve and leave behind fixture HTML in the real
    `data/cache` — a live scan could then ingest "Acme India" as a real listing,
    and one test's cached page would satisfy the next test's request.
    """
    from sources import fetcher

    monkeypatch.setattr(fetcher, "CACHE_DIR", str(tmp_path))


CARD_HTML = """
<li>
  <div class="base-card" data-entity-urn="urn:li:jobPosting:123456">
    <a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/123456?trk=guest"></a>
    <h3 class="base-search-card__title"> Site Reliability Engineer II </h3>
    <h4 class="base-search-card__subtitle"><a> Acme India </a></h4>
    <span class="job-search-card__location"> Bengaluru, Karnataka, India </span>
    <time datetime="2026-07-30">2 hours ago</time>
  </div>
</li>
"""


def test_parse_guest_cards_extracts_clean_fields():
    from scrapers.linkedin_guest import parse_guest_cards

    cards = parse_guest_cards(CARD_HTML)

    assert cards == [
        {
            "url": "https://www.linkedin.com/jobs/view/123456?trk=guest",
            "source_job_id": "123456",
            "title": "Site Reliability Engineer II",
            "company": "Acme India",
            "location": "Bengaluru, Karnataka, India",
            "posted": "2 hours ago",
        }
    ]


def test_searches_cover_city_and_remote_without_alias_duplication(monkeypatch):
    import config
    from scrapers import linkedin_guest

    monkeypatch.setattr(config, "search_titles", lambda limit: ["SRE", "MLOps Engineer"])
    monkeypatch.setattr(config, "search_locations", lambda limit: ["bangalore"])
    monkeypatch.setattr(config, "WANTS_REMOTE", True)
    monkeypatch.setattr(
        config, "CANDIDATE", {"location": "Bangalore, India"}, raising=False
    )

    assert linkedin_guest.build_searches() == [
        ("SRE", "bangalore", False),
        ("SRE", "India", True),
        ("MLOps Engineer", "bangalore", False),
        ("MLOps Engineer", "India", True),
    ]


def test_guest_fetch_dedupes_and_canonicalizes(monkeypatch):
    from scrapers import linkedin_guest

    class Response:
        status_code = 200
        text = CARD_HTML
        headers = {}

    class Session:
        def get(self, *args, **kwargs):
            return Response()

    monkeypatch.setattr(
        linkedin_guest, "build_searches", lambda: [("SRE", "Bangalore", False)] * 2
    )
    jobs, error = linkedin_guest.fetch_linkedin_guest(
        session=Session(), sleep_fn=lambda _: None
    )

    assert error == ""
    assert len(jobs) == 1
    assert jobs[0].url == "https://www.linkedin.com/jobs/view/123456"
    assert jobs[0].company == "Acme India"
    assert jobs[0].metadata["guest_search"] is True


def test_guest_fetch_surfaces_rate_limit_after_retry(monkeypatch):
    from scrapers import linkedin_guest

    class Response:
        status_code = 429
        text = ""
        headers = {"Retry-After": "0"}

    class Session:
        def get(self, *args, **kwargs):
            return Response()

    monkeypatch.setattr(
        linkedin_guest, "build_searches", lambda: [("SRE", "Bangalore", False)]
    )
    jobs, error = linkedin_guest.fetch_linkedin_guest(
        session=Session(), sleep_fn=lambda _: None
    )

    assert jobs == []
    assert "HTTP 429" in error


# ── Caching ──────────────────────────────────────────────────────────────────
#
# Guest search was 17.7s of every scan: 10 searches, each a request plus a
# deliberate 0.8-1.4s pace. The pacing is right — this is one host and there is
# 429 handling — so the lever is not sending the request twice in the first
# place. A cache hit is politeness as much as speed.


def test_a_cached_search_sends_no_request_and_does_not_sleep(monkeypatch):
    from scrapers import linkedin_guest

    calls, slept = [], []

    class Response:
        status_code = 200
        text = CARD_HTML
        headers = {}

    class Session:
        def get(self, *args, **kwargs):
            calls.append(1)
            return Response()

    monkeypatch.setattr(
        linkedin_guest, "build_searches", lambda: [("SRE", "Bangalore", False)]
    )

    first, _ = linkedin_guest.fetch_linkedin_guest(
        session=Session(), sleep_fn=slept.append
    )
    assert len(calls) == 1 and len(first) == 1
    sends_after_cold = len(calls)
    slept.clear()

    second, _ = linkedin_guest.fetch_linkedin_guest(
        session=Session(), sleep_fn=slept.append
    )
    assert len(calls) == sends_after_cold, "cached run still hit LinkedIn"
    assert slept == [], "slept for a request it never sent"
    assert [j.url for j in second] == [j.url for j in first]


def test_a_blocked_response_is_never_cached(monkeypatch):
    """Caching a 429 would keep the block alive for the whole TTL."""
    from scrapers import linkedin_guest

    class Blocked:
        status_code = 429
        text = ""
        headers = {"Retry-After": "0"}

    class Session:
        def get(self, *args, **kwargs):
            return Blocked()

    monkeypatch.setattr(
        linkedin_guest, "build_searches", lambda: [("SRE", "Bangalore", False)]
    )
    jobs, error = linkedin_guest.fetch_linkedin_guest(
        session=Session(), sleep_fn=lambda _: None
    )
    assert jobs == [] and "HTTP 429" in error

    from sources.fetcher import read_cached_text, text_cache_key

    key = text_cache_key(
        linkedin_guest.SEARCH_URL,
        {"keywords": "SRE", "location": "Bangalore", "start": 0, "sortBy": "DD"},
    )
    assert read_cached_text(key) is None
