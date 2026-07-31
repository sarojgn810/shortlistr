"""Discovery honesty — free sources first, Apify last, JD enrich for matches."""

from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))


def test_apify_always_runs_last():
    from sources.registry import SourceRegistry, _apify_last

    assert _apify_last(["apify", "naukri", "linkedin_guest"]) == [
        "naukri",
        "linkedin_guest",
        "apify",
    ]
    reg = SourceRegistry(
        enabled=["apify", "watchlist_ats", "linkedin_guest", "naukri"]
    )
    # Explicit list still reorders Apify last.
    assert reg.enabled[-1] == "apify"
    assert "linkedin_guest" in reg.enabled
    assert reg.enabled.index("linkedin_guest") < reg.enabled.index("apify")


def test_linkedin_apify_includes_onsite_when_city_and_remote():
    from sources.apify_boards import _linkedin_input

    both = _linkedin_input(
        "SRE", "bangalore", limit=40, experience=5, wants_remote=True, cfg={}
    )
    assert set(both["remote"]) == {"1", "2", "3"}

    remote_only = _linkedin_input(
        "SRE", "Remote", limit=40, experience=5, wants_remote=True, cfg={}
    )
    assert set(remote_only["remote"]) == {"2", "3"}

    onsite = _linkedin_input(
        "SRE", "bangalore", limit=40, experience=5, wants_remote=False, cfg={}
    )
    assert onsite["remote"] == ["1"]


def test_pipeline_feed_drops_off_target(tmp_path, monkeypatch):
    import config
    import store.db as db_mod
    from models.job import JobRecord
    from store import db as store
    from store.pipeline_feed import feed_jobs

    monkeypatch.setattr(db_mod, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(db_mod, "DB_PATH", str(tmp_path / "autojob.db"))
    monkeypatch.setattr(
        config,
        "SEARCH_KEYWORDS",
        ["site reliability engineer", "sre", "mlops"],
        raising=False,
    )
    monkeypatch.setattr(config, "LOCATION_KEYWORDS", ["bangalore", "remote"], raising=False)
    monkeypatch.setattr(config, "LOCATION_PREFERENCE_SET", True, raising=False)
    monkeypatch.setattr(config, "WANTS_REMOTE", True, raising=False)
    monkeypatch.setattr(config, "MIN_FIT_SCORE", 40, raising=False)
    monkeypatch.setattr(config, "REMOTE_STRICT", False, raising=False)
    monkeypatch.setattr(config, "DEAL_BREAKERS", [], raising=False)
    monkeypatch.setattr(config, "MIN_SALARY_INR_LPA", 0, raising=False)
    monkeypatch.setattr(config, "MIN_SALARY_USD", 0, raising=False)
    monkeypatch.setattr(config, "SALARY_UNLISTED", "include", raising=False)
    monkeypatch.setattr(config, "CANDIDATE", {"years_exp": 9}, raising=False)
    monkeypatch.setattr(config, "CV_MD_PATH", str(tmp_path / "cv.md"), raising=False)
    (tmp_path / "cv.md").write_text("# Ada\n\n## TECHNICAL SKILLS\nKubernetes, AWS\n", encoding="utf-8")

    store.init_db()
    keep = JobRecord(
        url="https://example.com/sre",
        source="Greenhouse",
        company="Acme",
        title="Site Reliability Engineer",
        location="Bangalore",
        jd_text="Kubernetes Prometheus Terraform on-call SRE platform. " * 5,
        fit_score=60,
        fit_reason="title match",
    )
    drop = JobRecord(
        url="https://example.com/marketing",
        source="Greenhouse",
        company="Acme",
        title="Marketing Coordinator",
        location="Bangalore",
        jd_text="Social media campaigns. " * 20,
        fit_score=0,
    )
    n = feed_jobs([keep, drop], export_markdown=False)
    assert n == 1
    with store.db() as conn:
        titles = [r[0] for r in conn.execute("SELECT title FROM jobs").fetchall()]
    assert titles == ["Site Reliability Engineer"]


def test_enrich_stub_skips_off_target_titles(tmp_path, monkeypatch):
    import config
    import store.db as db_mod
    from models.job import JobRecord
    from processors import enrich_jd
    from scrapers.browser_fetch import PageFetch
    from store import db as store

    monkeypatch.setattr(db_mod, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(db_mod, "DB_PATH", str(tmp_path / "autojob.db"))
    monkeypatch.setattr(
        config,
        "SEARCH_KEYWORDS",
        ["site reliability engineer", "sre"],
        raising=False,
    )
    monkeypatch.setattr(
        config, "LOCATION_KEYWORDS", ["bangalore", "bengaluru", "remote"], raising=False
    )
    monkeypatch.setattr(config, "LOCATION_PREFERENCE_SET", True, raising=False)
    monkeypatch.setattr(config, "WANTS_REMOTE", True, raising=False)
    monkeypatch.setattr(config, "MIN_FIT_SCORE", 40, raising=False)
    monkeypatch.setattr(config, "REMOTE_STRICT", False, raising=False)
    monkeypatch.setattr(config, "DEAL_BREAKERS", [], raising=False)
    monkeypatch.setattr(config, "MIN_SALARY_INR_LPA", 0, raising=False)
    monkeypatch.setattr(config, "MIN_SALARY_USD", 0, raising=False)
    monkeypatch.setattr(config, "SALARY_UNLISTED", "include", raising=False)
    monkeypatch.setattr(config, "CANDIDATE", {"years_exp": 9}, raising=False)
    monkeypatch.setattr(config, "CV_MD_PATH", str(tmp_path / "cv.md"), raising=False)
    (tmp_path / "cv.md").write_text(
        "# Ada\n\n## TECHNICAL SKILLS\nKubernetes, AWS, Prometheus\n", encoding="utf-8"
    )

    store.init_db()
    store.upsert_jobs(
        [
            JobRecord(
                url="https://example.com/sre",
                source="LinkedIn",
                company="Acme",
                title="Site Reliability Engineer",
                location="Bengaluru",
                jd_text="",
            ),
            JobRecord(
                url="https://example.com/mkt",
                source="LinkedIn",
                company="Acme",
                title="Marketing Manager",
                location="Bengaluru",
                jd_text="",
            ),
        ]
    )

    calls: list[str] = []

    def fake_fetch(url, allow_browser=True):
        calls.append(url)
        html = (
            "<html><body><h1>Role</h1><p>"
            + ("Kubernetes Prometheus Grafana on-call. " * 30)
            + "</p></body></html>"
        )
        return PageFetch(url=url, html=html, final_url=url, status=200, via="requests")

    monkeypatch.setattr(enrich_jd, "fetch_page", fake_fetch)
    result = enrich_jd.enrich_stub_jobs(limit=5, allow_browser=False, title_match_only=True)
    assert result["updated"] == 1
    assert result["skipped_off_target"] >= 1
    assert calls == ["https://example.com/sre"]
