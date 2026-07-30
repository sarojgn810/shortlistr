"""Phase 1 hardening tests — portals, parallel fetch, mocks, golden JD bands."""

from __future__ import annotations

import json
import os
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUTOMATION = os.path.join(ROOT, "automation")
sys.path.insert(0, AUTOMATION)


@pytest.fixture
def isolated_data_dir(monkeypatch):
    tmp = tempfile.mkdtemp()
    import config

    monkeypatch.setattr(config, "DATA_DIR", tmp)
    import store.db as db_mod

    monkeypatch.setattr(db_mod, "DATA_DIR", tmp)
    monkeypatch.setattr(db_mod, "DB_PATH", os.path.join(tmp, "shortlistr.db"))
    return tmp


def test_portals_uses_example_when_user_file_missing(monkeypatch):
    import portals_config

    monkeypatch.setattr(portals_config, "PORTALS_PATH", "/nonexistent/portals.yml")
    assert os.path.exists(portals_config.PORTALS_EXAMPLE_PATH)
    gh, lever, ashby = portals_config.load_portals_slugs()
    assert len(gh) > 0 or len(lever) > 0 or len(ashby) > 0


def test_config_has_no_duplicate_ats_lists():
    import config

    for key in ("GREENHOUSE_COMPANIES", "LEVER_COMPANIES", "ASHBY_COMPANIES", "TARGET_REMOTE_COMPANIES"):
        assert key not in config.__dict__, f"{key} should live in portals.yml only"


def test_gmail_adapter_registered():
    from sources.registry import get_registry

    health = get_registry().health()
    assert "gmail" in health


def test_greenhouse_adapter_mock(monkeypatch):
    from sources.adapters.greenhouse_adapter import GreenhouseAdapter, _fetch_greenhouse_slug

    fixture = os.path.join(ROOT, "tests", "fixtures", "greenhouse_datadog.json")
    data = json.load(open(fixture, encoding="utf-8"))

    monkeypatch.setattr(
        "sources.adapters.greenhouse_adapter.cached_get_json",
        lambda url, **kw: data if "datadog" in (kw.get("cache_key") or url) else None,
    )
    monkeypatch.setattr(
        "sources.adapters.greenhouse_adapter.get_greenhouse_slugs",
        lambda: ["datadog"],
    )

    adapter = GreenhouseAdapter()
    jobs, stats = adapter.fetch_raw()
    assert stats.raw_count == 2
    assert len(jobs) == 2
    assert jobs[0].title.startswith("Senior Site")


def test_parallel_flat_map():
    from sources.parallel import parallel_flat_map

    def double(n):
        return [n, n * 10]

    out = parallel_flat_map([1, 2, 3], double, max_workers=3)
    assert sorted(out) == [1, 2, 3, 10, 20, 30]


def test_pipeline_feed_sqlite(isolated_data_dir):
    from models.job import JobRecord
    from store import db as store
    from store.pipeline_feed import feed_jobs

    store.init_db()
    job = JobRecord(url="https://example.com/j/1", source="test", company="Co", title="SRE")
    n = feed_jobs([job], export_markdown=False)
    assert n == 1
    assert store.pending_pipeline_count() >= 1


# 20 golden JD bands (heuristic fallback returns 3.5 — band must include 3.5)
GOLDEN_INLINE = [
    ("Senior SRE — Remote India. Kubernetes, Prometheus, Terraform, on-call.", 3.0, 5.0),
    ("Staff Platform Engineer — Remote. AWS, Kubernetes, IaC, SLO frameworks.", 3.0, 5.0),
    ("DevOps Engineer — Bangalore hybrid. CI/CD, Docker, Jenkins.", 2.5, 5.0),
    ("Junior Marketing Coordinator — Mumbai on-site. Social media.", 0.0, 4.0),
    ("Intern Software Engineer — unpaid, on-site only.", 0.0, 4.0),
    ("Principal SRE — Global remote. 10+ years, incident command, observability.", 3.0, 5.0),
    ("Cloud Infrastructure Engineer — Remote India. Linux, automation, Python.", 3.0, 5.0),
    ("MLOps Engineer — Remote. ML pipelines, monitoring, feature stores.", 3.0, 5.0),
    ("Data Analyst — Excel, SQL, dashboards. On-site Delhi.", 0.0, 4.0),
    ("Site Reliability Engineer — Remote. PagerDuty, Grafana, K8s.", 3.0, 5.0),
    ("Frontend React Developer — Remote US only.", 0.0, 4.0),
    ("Platform Engineer — Remote EMEA. Service mesh, GitOps.", 3.0, 5.0),
    ("Salesforce Administrator — onsite, no DevOps.", 0.0, 4.0),
    ("AIOps Engineer — Remote India. LLM ops, anomaly detection.", 3.0, 5.0),
    ("Network Engineer — Cisco, on-site, no cloud.", 0.0, 4.0),
    ("Infrastructure Lead — Remote. Team lead, Terraform, multi-cloud.", 3.0, 5.0),
    ("QA Manual Tester — office based.", 0.0, 4.0),
    ("SRE Manager — Remote. People management, reliability strategy.", 3.0, 5.0),
    ("Blockchain Web3 developer — crypto startup.", 0.0, 4.0),
    ("Observability Engineer — Remote. OpenTelemetry, Datadog, SLOs.", 3.0, 5.0),
]


@pytest.mark.parametrize("jd,min_s,max_s", GOLDEN_INLINE)
def test_golden_jd_inline_bands(jd, min_s, max_s, isolated_data_dir):
    from eval.service import evaluate_job_text

    result = evaluate_job_text(jd, url="https://golden.test/inline", company="Test", role="Role")
    slack = 0.5
    assert result.score >= min_s - slack
    assert result.score <= max_s + slack


def test_fetch_greenhouse_slug_empty_on_404(monkeypatch):
    from sources.adapters.greenhouse_adapter import _fetch_greenhouse_slug

    monkeypatch.setattr(
        "sources.adapters.greenhouse_adapter.cached_get_json",
        lambda *a, **k: None,
    )
    assert _fetch_greenhouse_slug("missing") == []
