"""Public job APIs — Adzuna, Arbeitnow, Jobicy.

Official documented endpoints, not scrapes. Yield is honest rather than
exciting: against a Site Reliability Engineer profile, Arbeitnow returned 2
title matches from 175 postings and Jobicy 2 from 100 — and all four sat in the
UK / EMEA / APAC, so an India-scoped profile correctly keeps none of them.
They earn their place by being free and one request each, not by volume.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "automation"))


# ── Arbeitnow ────────────────────────────────────────────────────────────────

def test_arbeitnow_maps_a_posting(monkeypatch):
    from sources.adapters import public_feeds_adapter as pf

    monkeypatch.setattr("sources.fetcher.cached_get_json", lambda *a, **k: {
        "data": [{"title": "SRE", "company_name": "Acme", "location": "Berlin",
                  "url": "https://x.test/1", "description": "d", "remote": False}]
    })
    jobs = pf.fetch_arbeitnow()
    assert len(jobs) == 1
    assert jobs[0].source == "Arbeitnow" and jobs[0].company == "Acme"
    assert jobs[0].location == "Berlin"


def test_arbeitnow_marks_remote_in_the_location(monkeypatch):
    """The filter reads location text, so a remote flag has to reach it."""
    from sources.adapters import public_feeds_adapter as pf

    monkeypatch.setattr("sources.fetcher.cached_get_json", lambda *a, **k: {
        "data": [{"title": "SRE", "company_name": "A", "location": "Berlin",
                  "url": "https://x.test/1", "remote": True}]
    })
    assert "Remote" in pf.fetch_arbeitnow()[0].location


def test_a_posting_with_no_url_is_skipped(monkeypatch):
    """URL is the identity — without it a job cannot dedupe or be opened."""
    from sources.adapters import public_feeds_adapter as pf

    monkeypatch.setattr("sources.fetcher.cached_get_json", lambda *a, **k: {
        "data": [{"title": "SRE", "company_name": "A", "url": ""}]
    })
    assert pf.fetch_arbeitnow() == []


# ── Jobicy ───────────────────────────────────────────────────────────────────

def test_jobicy_maps_a_posting(monkeypatch):
    from sources.adapters import public_feeds_adapter as pf

    monkeypatch.setattr("sources.fetcher.cached_get_json", lambda *a, **k: {
        "jobs": [{"jobTitle": "SRE", "companyName": "Acme",
                  "jobGeo": "EMEA,  Italy", "url": "https://x.test/1",
                  "jobExcerpt": "d"}]
    })
    job = pf.fetch_jobicy()[0]
    assert job.source == "Jobicy"
    assert job.location == "EMEA, Italy", "the double space should be normalised"


def test_jobicy_without_a_geo_is_treated_as_remote(monkeypatch):
    from sources.adapters import public_feeds_adapter as pf

    monkeypatch.setattr("sources.fetcher.cached_get_json", lambda *a, **k: {
        "jobs": [{"jobTitle": "SRE", "companyName": "A", "jobGeo": "",
                  "url": "https://x.test/1"}]
    })
    assert pf.fetch_jobicy()[0].location == "Remote"


# ── Adzuna ───────────────────────────────────────────────────────────────────

def test_adzuna_is_a_silent_no_op_without_keys(monkeypatch):
    """It needs a free app id/key. Unconfigured must cost nothing and not warn."""
    from sources.adapters import public_feeds_adapter as pf

    monkeypatch.setattr("secrets_store.get_secret", lambda *a, **k: "")
    called = []
    monkeypatch.setattr("sources.fetcher.cached_get_json",
                        lambda *a, **k: called.append(1) or {})
    assert pf.fetch_adzuna() == []
    assert not called, "queried Adzuna with no credentials"


@pytest.mark.parametrize("locations,country", [
    (["bangalore", "india"], "in"),
    (["san francisco", "united states"], "us"),
    (["london"], "gb"),
    (["berlin", "germany"], "de"),
    (["singapore"], "sg"),
])
def test_adzuna_indexes_the_users_country(monkeypatch, locations, country):
    """Adzuna is per-country; an Indian search must not hit the US index."""
    import config as cfg
    from sources.adapters import public_feeds_adapter as pf

    monkeypatch.setattr(cfg, "LOCATION_KEYWORDS", locations)
    assert pf._adzuna_country() == country


def test_adzuna_queries_each_target_title(monkeypatch):
    """One query would hide every other role the profile asks for."""
    import config as cfg
    from sources.adapters import public_feeds_adapter as pf

    monkeypatch.setattr(cfg, "SEARCH_KEYWORDS", ["SRE", "MLOps Engineer"])
    monkeypatch.setattr(cfg, "LOCATION_KEYWORDS", ["india"])
    monkeypatch.setattr("secrets_store.get_secret", lambda name, *a, **k: "key")
    seen = []

    def fake(url, **kw):
        seen.append(kw.get("cache_key") or url)
        return {"results": []}

    monkeypatch.setattr("sources.fetcher.cached_get_json", fake)
    pf.fetch_adzuna()
    assert any("SRE" in s for s in seen) and any("MLOps" in s for s in seen)
    assert all("/in/" in s for s in seen), seen


def test_adzuna_dedupes_across_terms(monkeypatch):
    from sources.adapters import public_feeds_adapter as pf
    import config as cfg

    monkeypatch.setattr(cfg, "SEARCH_KEYWORDS", ["SRE", "Senior SRE"])
    monkeypatch.setattr(cfg, "LOCATION_KEYWORDS", ["india"])
    monkeypatch.setattr("secrets_store.get_secret", lambda name, *a, **k: "key")
    monkeypatch.setattr("sources.fetcher.cached_get_json", lambda *a, **k: {
        "results": [{"redirect_url": "https://x.test/1", "title": "SRE",
                     "company": {"display_name": "A"},
                     "location": {"display_name": "Bengaluru"}}]
    })
    assert len(pf.fetch_adzuna()) == 1


# ── the adapter ──────────────────────────────────────────────────────────────

def test_one_dead_feed_does_not_empty_the_source(monkeypatch):
    from sources.adapters import public_feeds_adapter as pf

    def boom():
        raise RuntimeError("feed is down")

    monkeypatch.setattr(pf, "_FEEDS", (
        ("Good", lambda: [object()]),
        ("Bad", boom),
    ))
    jobs, stats = pf.PublicFeedsAdapter().fetch_raw()
    assert len(jobs) == 1
    assert stats.raw_count == 1


def test_feeds_run_together(monkeypatch, overlap_gate):
    from sources.adapters import public_feeds_adapter as pf

    feeds = 4
    # parallel_call pools at min(10, len(fns)), so all four run together.
    gate, ran_alone = overlap_gate(feeds)

    def one():
        gate()
        return [object()]

    monkeypatch.setattr(pf, "_FEEDS", tuple((f"F{i}", one) for i in range(feeds)))
    pf.PublicFeedsAdapter().fetch_raw()

    assert not ran_alone.is_set(), "feeds ran one at a time"


def test_the_adapter_is_registered():
    from sources.registry import SourceRegistry

    names = [a.name for a in SourceRegistry().adapters()]
    assert "public_feeds" in names


# ── the retired Monster board ────────────────────────────────────────────────

def test_monster_is_retired_with_a_reason():
    """bebity/monster-jobs-scraper 404s; a board that cannot run must say so
    rather than fail a scan and count toward tripping the circuit breaker."""
    from sources.apify_boards import BOARD_REGISTRY, BOARD_SKIPPED

    assert "monster" not in BOARD_REGISTRY
    assert "monster" in BOARD_SKIPPED
    assert BOARD_SKIPPED["monster"]


def test_every_remaining_apify_board_has_an_input_builder():
    """A registry entry with no builder would explode at run time, not import."""
    from sources.apify_boards import BOARD_REGISTRY

    for board_id, spec in BOARD_REGISTRY.items():
        assert callable(spec.get("input")), board_id
        assert spec.get("actor"), board_id


# ── Jobgether, and why Jobsora is absent ─────────────────────────────────────

def test_jobgether_only_crawls_categories_the_profile_wants(monkeypatch):
    """563 categories exist; crawling all of them to keep none would be rude."""
    import config as cfg
    from scrapers import jobgether_scraper as jg

    monkeypatch.setattr(cfg, "SEARCH_KEYWORDS", ["DevOps Architect"])
    monkeypatch.setattr(jg, "_fetch", lambda url, timeout=20: (
        "<urlset>"
        "<url><loc>https://jobgether.com/remote-jobs/devops-architect</loc></url>"
        "<url><loc>https://jobgether.com/remote-jobs/treasury-operations-manager</loc></url>"
        "<url><loc>https://jobgether.com/remote-jobs/people-operations-specialist</loc></url>"
        "</urlset>"
    ))
    monkeypatch.setattr("sources.fetcher.read_cached_text", lambda *a, **k: None)
    monkeypatch.setattr("sources.fetcher.write_cached_text", lambda *a, **k: None)

    cats = jg._relevant_categories()
    assert cats == ["https://jobgether.com/remote-jobs/devops-architect"], cats


def test_a_profile_with_no_matching_category_crawls_nothing(monkeypatch):
    """Jobgether has no site-reliability-engineer category; do not guess a near one."""
    import config as cfg
    from scrapers import jobgether_scraper as jg

    monkeypatch.setattr(cfg, "SEARCH_KEYWORDS", ["Site Reliability Engineer"])
    monkeypatch.setattr(jg, "_fetch", lambda url, timeout=20: (
        "<urlset><url><loc>https://jobgether.com/remote-jobs/devops-architect</loc></url></urlset>"
    ))
    monkeypatch.setattr("sources.fetcher.read_cached_text", lambda *a, **k: None)
    monkeypatch.setattr("sources.fetcher.write_cached_text", lambda *a, **k: None)
    assert jg._relevant_categories() == []
    assert jg.fetch_jobgether_raw() == []


def test_template_placeholder_offers_are_skipped():
    """robots.txt disallows /offer/{*}; they render as a job titled "Undefined"."""
    from scrapers.jobgether_scraper import _offers_from_category

    html = (
        '<a href="/offer/{id}-undefined">x</a>'
        '<img alt="Acme"><a href="/offer/6a219b51f8af0ea2c40516fe-devops-architect">y</a>'
    )
    offers = _offers_from_category(html)
    assert [p for p, _ in offers] == ["/offer/6a219b51f8af0ea2c40516fe-devops-architect"]
    assert offers[0][1] == "Acme"


def test_the_hex_id_is_stripped_from_the_title():
    from scrapers.jobgether_scraper import _title_from_slug

    title = _title_from_slug("/offer/6a219b51f8af0ea2c40516fe-senior-site-reliability-engineer")
    assert title == "Senior Site Reliability Engineer"


def test_jobgether_honours_the_published_crawl_delay():
    """Their robots.txt asks for 2 seconds between requests."""
    from scrapers.jobgether_scraper import CRAWL_DELAY

    assert CRAWL_DELAY >= 2.0


def test_jobsora_is_not_a_source():
    """Its robots.txt disallows /vacancy/, /vacancy-search/ and every ?query URL
    — every path that has a job on it. There is no permitted way in."""
    import os

    root = os.path.join(os.path.dirname(__file__), "..", "automation")
    hits = []
    for dirpath, _dirs, files in os.walk(root):
        if "__pycache__" in dirpath:
            continue
        for f in files:
            if not f.endswith(".py"):
                continue
            path = os.path.join(dirpath, f)
            with open(path, encoding="utf-8", errors="ignore") as fh:
                body = fh.read()
            if "jobsora.com" in body.lower():
                hits.append(path)
    assert not hits, f"jobsora.com is fetched somewhere: {hits}"
