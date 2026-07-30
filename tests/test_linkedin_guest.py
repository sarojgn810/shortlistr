"""Free LinkedIn guest discovery stays profile-driven and scrape-only."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "automation"))


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
