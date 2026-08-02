"""SmartRecruiters is asked for the role, not swept.

The postings API caps a page at 100. Freshworks has 154 openings, so the old
sweep silently never saw 54 of them — invisible, with nothing in the logs to say
so. Paging with a query removes that blind spot and cuts the raw volume from 100
to 35 on that board.

Note the API's `q` is fuzzy full text, not a title match: querying "Site
Reliability Engineer" returns "Principal Engineer" and even "Customer Success
Manager". So this narrows what is downloaded, and pipeline/filter.py still
decides what is relevant. It is not a replacement for the title gate.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "automation"))


def _page(names, total=None, remote=False):
    return {
        "totalFound": total if total is not None else len(names),
        "content": [
            {
                "id": f"id-{n}",
                "name": n,
                "location": {"city": "Chennai", "country": "in"} if not remote else {"remote": True},
                "company": {"name": "Freshworks"},
                "department": {"label": "Eng"},
            }
            for n in names
        ],
    }


# ── queries ──────────────────────────────────────────────────────────────────

def test_each_target_title_becomes_its_own_query(monkeypatch):
    import config as cfg
    from scrapers import smartrecruiters_scraper as sr

    monkeypatch.setattr(cfg, "SEARCH_KEYWORDS", ["SRE", "Site Reliability Engineer"])
    terms = sr._search_terms()
    assert terms[0] == "Site Reliability Engineer", "most specific query first"
    assert "SRE" in terms


def test_no_targeting_takes_the_whole_board(monkeypatch):
    import config as cfg
    from scrapers import smartrecruiters_scraper as sr

    monkeypatch.setattr(cfg, "SEARCH_KEYWORDS", [])
    assert sr._search_terms() == [""]


def test_the_term_list_is_capped(monkeypatch):
    import config as cfg
    from scrapers import smartrecruiters_scraper as sr

    monkeypatch.setattr(cfg, "SEARCH_KEYWORDS", [f"Role {i}" for i in range(20)])
    assert len(sr._search_terms()) == sr.MAX_SEARCH_TERMS


def test_the_query_reaches_the_api(monkeypatch):
    import config as cfg
    from scrapers import smartrecruiters_scraper as sr

    monkeypatch.setattr(cfg, "SEARCH_KEYWORDS", ["Site Reliability Engineer"])
    seen = []

    def fake_get(url, **kw):
        seen.append(url)
        return _page(["Site Reliability Engineer"])

    monkeypatch.setattr("sources.fetcher.cached_get_json", fake_get)
    sr._scrape_company("Freshworks")
    assert any("q=Site+Reliability+Engineer" in u for u in seen), seen


def test_one_title_can_never_hide_another(monkeypatch):
    import config as cfg
    from scrapers import smartrecruiters_scraper as sr

    monkeypatch.setattr(cfg, "SEARCH_KEYWORDS", ["SRE", "MLOps Engineer"])

    def fake_get(url, **kw):
        if "q=MLOps" in url:
            return _page(["MLOps Engineer"])
        if "q=SRE" in url:
            return _page(["Site Reliability Engineer"])
        return _page([])

    monkeypatch.setattr("sources.fetcher.cached_get_json", fake_get)
    titles = sorted(j.title for j in sr._scrape_company("Freshworks"))
    assert titles == ["MLOps Engineer", "Site Reliability Engineer"]


def test_overlapping_terms_do_not_duplicate_a_posting(monkeypatch):
    import config as cfg
    from scrapers import smartrecruiters_scraper as sr

    monkeypatch.setattr(cfg, "SEARCH_KEYWORDS", ["SRE", "Senior SRE"])
    monkeypatch.setattr("sources.fetcher.cached_get_json",
                        lambda url, **kw: _page(["Senior SRE"]))
    assert len(sr._scrape_company("Freshworks")) == 1


# ── the 100-cap blind spot ───────────────────────────────────────────────────

def test_a_board_bigger_than_one_page_is_fully_walked(monkeypatch):
    """154 openings behind a 100 limit: 54 were never fetched."""
    import config as cfg
    from scrapers import smartrecruiters_scraper as sr

    monkeypatch.setattr(cfg, "SEARCH_KEYWORDS", [])  # single "" term, whole board

    def fake_get(url, **kw):
        offset = 100 if "offset=100" in url else 0
        names = [f"Role {i}" for i in range(offset, min(offset + 100, 154))]
        return _page(names, total=154)

    monkeypatch.setattr("sources.fetcher.cached_get_json", fake_get)
    assert len(sr._scrape_company("Freshworks")) == 154


def test_paging_stops_and_does_not_loop_forever(monkeypatch):
    import config as cfg
    from scrapers import smartrecruiters_scraper as sr

    monkeypatch.setattr(cfg, "SEARCH_KEYWORDS", [])
    calls = []

    def fake_get(url, **kw):
        calls.append(url)
        return _page([f"Role {i}" for i in range(100)], total=100)

    monkeypatch.setattr("sources.fetcher.cached_get_json", fake_get)
    sr._scrape_company("Freshworks")
    assert len(calls) <= 3, f"paged {len(calls)} times on a 100-job board"


# ── location must never be invented ──────────────────────────────────────────

def test_a_missing_location_stays_empty(monkeypatch):
    """It used to default to 'Remote / India', tagging worldwide roles Indian.

    An empty location passes the gate by design (a posting that does not say
    where it is should not be discarded); a *wrong* one silently smuggles
    off-target rows past it.
    """
    from scrapers import smartrecruiters_scraper as sr

    rec = sr._record({"id": "1", "name": "SRE", "location": {}}, "acme", "2026-08-02")
    assert rec is not None
    assert rec.location == ""


def test_a_remote_flag_is_honoured():
    from scrapers import smartrecruiters_scraper as sr

    rec = sr._record({"id": "1", "name": "SRE", "location": {"remote": True}},
                     "acme", "2026-08-02")
    assert rec.location == "Remote"


def test_city_and_country_are_joined():
    from scrapers import smartrecruiters_scraper as sr

    rec = sr._record({"id": "1", "name": "SRE",
                      "location": {"city": "Chennai", "country": "in"}},
                     "acme", "2026-08-02")
    assert rec.location == "Chennai, in"


def test_a_posting_with_no_id_is_skipped():
    """Without an id there is no stable URL, so it cannot be deduped or reopened."""
    from scrapers import smartrecruiters_scraper as sr

    assert sr._record({"name": "SRE"}, "acme", "2026-08-02") is None


# ── boards run together ──────────────────────────────────────────────────────

def test_boards_are_fetched_in_parallel(monkeypatch):
    import time

    from scrapers import smartrecruiters_scraper as sr

    tracker = {"in_flight": 0, "peak": 0}

    def slow(slug):
        tracker["in_flight"] += 1
        tracker["peak"] = max(tracker["peak"], tracker["in_flight"])
        try:
            time.sleep(0.2)
            return [f"job-{slug}"]
        finally:
            tracker["in_flight"] -= 1

    monkeypatch.setattr(sr, "_scrape_company", slow)
    t0 = time.monotonic()
    out = sr.fetch_smartrecruiters_raw([f"co{i}" for i in range(6)])
    assert len(out) == 6
    assert tracker["peak"] > 1, "boards were fetched one at a time"
    assert time.monotonic() - t0 < 6 * 0.2 * 0.6


def test_one_dead_board_does_not_lose_the_others(monkeypatch):
    from scrapers import smartrecruiters_scraper as sr

    def flaky(slug):
        if slug == "bad":
            raise RuntimeError("board is down")
        return [f"job-{slug}"]

    monkeypatch.setattr(sr, "_scrape_company", flaky)
    assert sorted(sr.fetch_smartrecruiters_raw(["good1", "bad", "good2"])) == [
        "job-good1", "job-good2"
    ]
