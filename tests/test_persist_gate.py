"""Persist gate — only profile keepers land in the user DB."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "automation"))


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    import config
    import store.db as db_mod

    monkeypatch.setattr(db_mod, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(db_mod, "DB_PATH", str(tmp_path / "shortlistr.db"))
    monkeypatch.setattr(config, "SHORTLISTR_ROOT", str(tmp_path))
    monkeypatch.setattr(config, "SEARCH_KEYWORDS", ["Site Reliability Engineer", "SRE"])
    monkeypatch.setattr(config, "LOCATION_KEYWORDS", ["hyderabad", "bengaluru"])
    monkeypatch.setattr(config, "LOCATION_PREFERENCE_SET", True)
    monkeypatch.setattr(config, "WANTS_REMOTE", False)
    monkeypatch.setattr(config, "REMOTE_STRICT", False)
    monkeypatch.setattr(config, "MIN_FIT_SCORE", 40)
    yield tmp_path


def _job(**kwargs):
    from models.job import JobRecord

    base = dict(
        url="https://example.com/jobs/1",
        source="test",
        company="Acme",
        title="Site Reliability Engineer",
        location="Hyderabad",
        jd_text="Kubernetes Terraform Prometheus on-call SLOs. " * 8,
        fit_score=80,
        metadata={"discovery_relevance": "relevant"},
    )
    base.update(kwargs)
    return JobRecord(**base)


def test_jobs_for_user_db_drops_off_target(isolated):
    from orchestrator.discovery import jobs_for_user_db

    keepers, gate = jobs_for_user_db(
        [
            _job(url="https://example.com/a", metadata={"discovery_relevance": "relevant"}),
            _job(
                url="https://example.com/b",
                title="Account Executive",
                metadata={"discovery_relevance": "off_target"},
                fit_score=90,
            ),
        ]
    )
    assert len(keepers) == 1
    assert gate["kept"] == 1
    assert gate["dropped_off_target"] == 1
    assert gate["dropped_low_fit"] == 0


def test_jobs_for_user_db_drops_low_fit(isolated):
    from orchestrator.discovery import jobs_for_user_db

    keepers, gate = jobs_for_user_db(
        [
            _job(url="https://example.com/hi", fit_score=80),
            _job(url="https://example.com/lo", fit_score=10),
        ]
    )
    assert len(keepers) == 1
    assert gate["dropped_low_fit"] == 1


def test_persist_discovered_skips_off_target_and_low_fit(isolated):
    from orchestrator.discovery import persist_discovered
    from store import db as store

    store.init_db()
    n = persist_discovered(
        [
            _job(url="https://example.com/keep", fit_score=75),
            _job(
                url="https://example.com/off",
                title="Product Manager",
                metadata={"discovery_relevance": "off_target"},
                fit_score=90,
            ),
            _job(url="https://example.com/low", fit_score=5),
        ]
    )
    assert n == 1
    with store.db() as conn:
        urls = [
            r["url"]
            for r in conn.execute("SELECT url FROM jobs ORDER BY url").fetchall()
        ]
    assert urls == ["https://example.com/keep"]


def test_discover_and_filter_persist_gate_stats(isolated, monkeypatch):
    import orchestrator.discovery as disc
    from sources.base import FetchStats

    class StubAdapter:
        name = "stub"

        def fetch_raw(self, log_totals=False):
            return [
                _job(
                    url="https://example.com/sre",
                    title="Senior SRE",
                    location="Hyderabad",
                    jd_text="kubernetes terraform prometheus grafana",
                ),
                _job(
                    url="https://example.com/pm",
                    title="Product Manager",
                    location="Berlin",
                    jd_text="roadmap stakeholders",
                    fit_score=0,
                ),
            ], FetchStats(source=self.name, raw_count=2)

    monkeypatch.setattr(
        disc,
        "get_registry",
        lambda: type("R", (), {"adapters": lambda self: [StubAdapter()]})(),
    )

    keepers, rejected, stats = disc.discover_and_filter()
    gate = stats["persist_gate"]
    assert gate["fetched"] == 2
    assert gate["kept"] == len(keepers)
    assert gate["kept"] >= 1
    assert gate["dropped_off_target"] >= 1
    assert all(
        (j.metadata or {}).get("discovery_relevance") == "relevant" for j in keepers
    )
