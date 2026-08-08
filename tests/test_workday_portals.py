"""Workday board parsing from portals / ATS detection URLs."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "automation"))


def test_parse_workday_url_strips_locale_and_deep_paths():
    from portals_config import parse_workday_url

    assert parse_workday_url(
        "https://zendesk.wd1.myworkdayjobs.com/en-US/zendesk"
    ) == ("zendesk", "1", "zendesk")
    assert parse_workday_url(
        "https://paloaltonetworks.wd5.myworkdayjobs.com/en-US/panwexternalcareers/introduction"
    ) == ("paloaltonetworks", "5", "panwexternalcareers")
    assert parse_workday_url("https://workday.wd5.myworkdayjobs.com/Workday") == (
        "workday",
        "5",
        "Workday",
    )
    assert parse_workday_url("https://example.com/careers") is None


def test_get_workday_boards_from_portals(tmp_path, monkeypatch):
    import portals_config as pc
    import yaml

    portals = tmp_path / "portals.yml"
    portals.write_text(
        yaml.safe_dump(
            {
                "tracked_companies": [
                    {
                        "name": "Zendesk",
                        "careers_url": "https://zendesk.wd1.myworkdayjobs.com/en-US/zendesk",
                        "scan_method": "workday",
                        "enabled": True,
                    },
                    {
                        "name": "Ignore Me",
                        "careers_url": "https://example.com/careers",
                        "scan_method": "playwright",
                        "enabled": True,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(pc, "PORTALS_PATH", str(portals))
    monkeypatch.setattr(pc, "PORTALS_EXAMPLE_PATH", str(tmp_path / "missing.yml"))

    boards = pc.get_workday_boards()
    assert boards == [("zendesk", "1", "zendesk", "Zendesk")]


# ── Boards are fetched in parallel ───────────────────────────────────────────
#
# Workday was ~97% of a full scan: 15 boards walked one at a time, and five
# tenants answered in ~34s each against 1-8s for the rest. Same 60 postings
# either way — the cost was waiting on slow hosts in series. Each board is a
# different myworkdayjobs tenant, so overlapping them adds no load per host.


def test_boards_are_scraped_concurrently(monkeypatch, overlap_gate):
    """Every board must be in flight at once, not walked one after another."""
    from scrapers import workday_scraper as ws

    boards = [(f"tenant{i}", "1", "site", f"Co {i}") for i in range(8)]
    monkeypatch.setattr(ws, "_company_list", lambda: boards)

    # fetch_workday_raw pools at min(10, len(boards)), so all eight run together.
    gate, ran_alone = overlap_gate(len(boards))

    def fake_scrape(tenant, wd_n, site, *, display_name=None):
        gate()
        return [f"job-{tenant}"]

    monkeypatch.setattr(ws, "_scrape_company", fake_scrape)
    jobs = ws.fetch_workday_raw()

    assert not ran_alone.is_set(), "boards were scraped one at a time"
    assert len(jobs) == len(boards), "every board must still be scraped"


def test_one_failing_board_does_not_lose_the_others(monkeypatch):
    """A dead tenant must not take the whole Workday source down with it."""
    from scrapers import workday_scraper as ws

    boards = [("good1", "1", "s", "Good 1"), ("bad", "1", "s", "Bad"),
              ("good2", "1", "s", "Good 2")]
    monkeypatch.setattr(ws, "_company_list", lambda: boards)

    def fake_scrape(tenant, wd_n, site, *, display_name=None):
        if tenant == "bad":
            raise RuntimeError("tenant is down")
        return [f"job-{tenant}"]

    monkeypatch.setattr(ws, "_scrape_company", fake_scrape)

    jobs = ws.fetch_workday_raw()
    assert sorted(jobs) == ["job-good1", "job-good2"]


# ── Search by keyword, do not sweep the whole board ──────────────────────────
#
# The board used to be fetched with an empty searchText and filtered locally.
# That is not only wasteful, it loses jobs: pagination stops at 60 postings, so
# at a large employer every matching role sits past the window. Measured across
# the real watchlist — empty search returned 811 postings and 1 keeper; searching
# by title returned 658 and 16.


def test_each_target_title_becomes_its_own_query(monkeypatch):
    from scrapers import workday_scraper as ws

    import config as cfg
    monkeypatch.setattr(cfg, "SEARCH_KEYWORDS",
                        ["SRE", "Site Reliability Engineer", "MLOps Engineer"])
    terms = ws._search_terms()
    assert "SRE" in terms and "Site Reliability Engineer" in terms
    # Longest first: the specific query is the better one to spend a request on.
    assert terms[0] == "Site Reliability Engineer"


def test_no_targeting_falls_back_to_the_whole_board(monkeypatch):
    """Without titles there is no query to send — do not invent one."""
    from scrapers import workday_scraper as ws

    import config as cfg
    monkeypatch.setattr(cfg, "SEARCH_KEYWORDS", [])
    assert ws._search_terms() == [""]


def test_the_term_list_is_capped(monkeypatch):
    """Each term is one request per board; an unbounded profile must not fan out."""
    from scrapers import workday_scraper as ws

    import config as cfg
    monkeypatch.setattr(cfg, "SEARCH_KEYWORDS", [f"Title {i}" for i in range(20)])
    assert len(ws._search_terms()) == ws.MAX_SEARCH_TERMS


def test_one_title_can_never_hide_another(monkeypatch):
    """The bug that made this an empty search: a single hardcoded query.

    Each term is asked separately and the results unioned, so a board whose SRE
    roles do not mention MLOps still contributes its MLOps roles.
    """
    from scrapers import workday_scraper as ws

    import config as cfg
    monkeypatch.setattr(cfg, "SEARCH_KEYWORDS", ["SRE", "MLOps Engineer"])
    monkeypatch.setattr(ws, "_company_list", lambda: [("acme", "1", "s", "Acme")])

    by_term = {
        "MLOps Engineer": [{"title": "MLOps Engineer", "externalPath": "/job/mlops",
                            "locationsText": "Remote"}],
        "SRE": [{"title": "Site Reliability Engineer", "externalPath": "/job/sre",
                 "locationsText": "Remote"}],
    }

    def fake_post(url, payload, **kw):
        if payload["offset"]:
            return {"jobPostings": []}
        return {"jobPostings": by_term.get(payload["searchText"], [])}

    monkeypatch.setattr("sources.fetcher.cached_post_json", fake_post)
    titles = sorted(j.title for j in ws.fetch_workday_raw())
    assert titles == ["MLOps Engineer", "Site Reliability Engineer"]


def test_overlapping_terms_do_not_duplicate_a_posting(monkeypatch):
    """'Senior SRE' and 'SRE' return many of the same rows."""
    from scrapers import workday_scraper as ws

    import config as cfg
    monkeypatch.setattr(cfg, "SEARCH_KEYWORDS", ["SRE", "Senior SRE"])
    monkeypatch.setattr(ws, "_company_list", lambda: [("acme", "1", "s", "Acme")])

    def fake_post(url, payload, **kw):
        if payload["offset"]:
            return {"jobPostings": []}
        return {"jobPostings": [{"title": "Senior SRE", "externalPath": "/job/1",
                                 "locationsText": "Remote"}]}

    monkeypatch.setattr("sources.fetcher.cached_post_json", fake_post)
    jobs = ws.fetch_workday_raw()
    assert len(jobs) == 1, "the same posting was returned by two terms and kept twice"
