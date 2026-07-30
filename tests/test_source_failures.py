"""Silent zero-result sources must surface as unhealthy, not success."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "automation"))


def test_ashby_rejects_schema_errors(monkeypatch):
    from scrapers import ashby_scraper

    class Response:
        status_code = 200

        def json(self):
            return {
                "errors": [
                    {
                        "message": 'Cannot query field "isRemote" on type "JobPostingBriefsWithIdsAndTeamId".'
                    }
                ]
            }

    monkeypatch.setattr(
        ashby_scraper.requests, "post", lambda *a, **k: Response()
    )
    jobs, error = ashby_scraper._fetch_ashby_slug_result("cohere")
    assert jobs == []
    assert "isRemote" in error


def test_ashby_parses_current_schema(monkeypatch):
    from scrapers import ashby_scraper

    class Response:
        status_code = 200

        def json(self):
            return {
                "data": {
                    "jobBoard": {
                        "teams": [{"id": "t1", "name": "Platform"}],
                        "jobPostings": [
                            {
                                "id": "abc-123",
                                "title": "Site Reliability Engineer",
                                "teamId": "t1",
                                "locationName": "Bengaluru",
                                "employmentType": "FullTime",
                                "secondaryLocations": [{"locationName": "Remote"}],
                            }
                        ],
                    }
                }
            }

    monkeypatch.setattr(
        ashby_scraper.requests, "post", lambda *a, **k: Response()
    )
    jobs, error = ashby_scraper._fetch_ashby_slug_result("cohere")
    assert error == ""
    assert len(jobs) == 1
    assert jobs[0].url == "https://jobs.ashbyhq.com/cohere/abc-123"
    assert jobs[0].location == "Bengaluru; Remote"
    assert jobs[0].department == "Platform"


def test_naukri_adapter_surfaces_captcha(monkeypatch):
    from scrapers.naukri_scraper import NaukriBlockedError
    from sources.adapters.naukri_adapter import NaukriAdapter

    def boom():
        raise NaukriBlockedError("Naukri public search requires CAPTCHA (HTTP 406)")

    monkeypatch.setattr("scrapers.naukri_scraper.scrape_naukri", boom)
    jobs, stats = NaukriAdapter().fetch_raw()
    assert jobs == []
    assert "CAPTCHA" in stats.error


def test_duckduckgo_anomaly_is_a_failure(monkeypatch):
    from processors import search_discovery

    class Response:
        status_code = 202
        text = "<html>anomaly detected</html>"

    monkeypatch.setattr(
        search_discovery.requests, "post", lambda *a, **k: Response()
    )
    try:
        search_discovery._run_duckduckgo("SRE Bangalore")
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "challenged" in str(exc).lower()


def test_source_error_counts_as_circuit_failure(monkeypatch, tmp_path):
    from orchestrator import discovery as disc
    from sources import circuit
    from sources.base import FetchStats

    monkeypatch.setattr(circuit, "STATE_PATH", str(tmp_path / "circuits.json"))

    class BadAdapter:
        name = "naukri"

        def fetch_raw(self, log_totals: bool = False):
            return [], FetchStats(source="naukri", error="CAPTCHA", raw_count=0)

    monkeypatch.setattr(
        disc,
        "get_registry",
        lambda: type("R", (), {"adapters": lambda self: [BadAdapter()]})(),
    )
    disc.discover_all()
    assert circuit._load()["naukri"]["failures"] == 1
