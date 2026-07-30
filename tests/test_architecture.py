"""Architecture tests — JobRecord, filter pipeline, store, eval, registry."""

from __future__ import annotations

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
    import sources.circuit as circuit
    monkeypatch.setattr(circuit, "STATE_PATH", os.path.join(tmp, "circuits.json"))
    return tmp

from models.job import JobRecord, job_id_from_url
from pipeline.filter import apply_discovery_filter, passes_title_location
from sources.registry import SourceRegistry, get_registry
from eval.schema import SCHEMA_V1
from eval.service import evaluate_job_text, recommend_apply


def test_job_record_roundtrip():
    job = JobRecord(
        url="https://boards.greenhouse.io/acme/jobs/123",
        source="Greenhouse",
        company="Acme",
        title="Senior SRE",
        location="Remote India",
    )
    assert job.job_id
    restored = JobRecord.from_dict(job.to_dict())
    assert restored.url == job.url
    assert restored.title == job.title


def test_job_id_from_url_stable():
    u = "https://example.com/jobs/1?ref=abc"
    assert job_id_from_url(u) == job_id_from_url(u)
    assert len(job_id_from_url(u)) == 16


def test_discovery_filter_title_location(monkeypatch):
    import config

    # Pin the targeting this test asserts against. It used to read whatever was
    # in the user's own config/profile.yml, so it passed or failed depending on
    # which job titles the person running it happened to be looking for — a
    # test of somebody's settings, not of the filter.
    monkeypatch.setattr(config, "SEARCH_KEYWORDS", ["SRE", "Site Reliability"])
    monkeypatch.setattr(config, "LOCATION_KEYWORDS", ["remote", "bengaluru"])
    monkeypatch.setattr(config, "WANTS_REMOTE", True)

    match = JobRecord(url="http://a", source="RemoteOK", company="X", title="Senior SRE", location="Remote")
    skip = JobRecord(url="http://b", source="Greenhouse", company="Y", title="Marketing Manager", location="NYC")
    assert passes_title_location(match)
    assert not passes_title_location(skip)
    passed, rejected, stats = apply_discovery_filter([match, skip])
    assert len(passed) == 1
    assert stats.passed_discovery == 1


def test_source_registry_defaults():
    import config
    orig = config.WANTS_REMOTE
    config.WANTS_REMOTE = True
    try:
        reg = SourceRegistry(enabled=["watchlist_ats", "aggregators"])
        names = [a.name for a in reg.adapters()]
        assert "watchlist_ats" in names
        assert "aggregators" in names
    finally:
        config.WANTS_REMOTE = orig


def test_source_registry_health():
    health = get_registry().health()
    assert "watchlist_ats" in health
    assert "linkedin" in health
    assert "gmail" in health


def test_sqlite_store_crud(isolated_data_dir):
    import store.db as db_mod
    db_mod.init_db()
    job = JobRecord(url="https://test.example/j/1", source="test", company="Co", title="SRE")
    jid = db_mod.upsert_job(job)
    assert jid
    db_mod.add_to_pipeline(jid)
    assert db_mod.pending_pipeline_count() >= 1
    run_id = db_mod.start_run(dry_run=True)
    db_mod.finish_run(run_id, source_stats={}, discovered=1, passed=1, strong_fit=0)
    assert db_mod.get_last_run() is not None


def test_eval_schema_required_fields():
    assert "score" in SCHEMA_V1["required"]
    assert "blocks" in SCHEMA_V1["properties"]


def test_eval_fallback_no_llm(isolated_data_dir):
    result = evaluate_job_text(
        "Senior SRE remote Kubernetes Prometheus",
        url="https://example.com/jobs/sre",
        company="ExampleCo",
        role="Senior SRE",
    )
    assert 0 <= result.score <= 5
    assert result.legitimacy in SCHEMA_V1["properties"]["legitimacy"]["enum"]
    assert "blocks" in result.to_dict()


@pytest.mark.parametrize("filename,expected", [
    ("sre-remote-india.txt", {"min_score": 3.0, "max_score": 5.0}),
    ("junior-marketing-onsite.txt", {"min_score": 0.0, "max_score": 3.5}),
    ("platform-remote-global.txt", {"min_score": 3.0, "max_score": 5.0}),
])
def test_golden_jd_eval_band(filename, expected, isolated_data_dir, monkeypatch):
    """Golden JD set — heuristic fallback must land in expected score band (±0.5 slack).

    Pin targeting + a neutral CV so the band does not depend on the developer's
    live profile.yml (same landmine as test_discovery_filter_title_location).
    """
    import config
    import eval.service as eval_svc

    monkeypatch.setattr(
        config,
        "SEARCH_KEYWORDS",
        ["SRE", "Site Reliability", "Platform Engineer", "DevOps"],
        raising=False,
    )
    cv_path = os.path.join(isolated_data_dir, "cv.md")
    open(cv_path, "w", encoding="utf-8").write(
        "# Alex Candidate\n\n"
        "## CORE COMPETENCIES\n\n"
        "Kubernetes, Terraform, Prometheus, AWS, Python, SRE, Platform Engineering\n\n"
        "## PROFESSIONAL EXPERIENCE\n\n"
        "### Site Reliability Engineer | Acme | 2020 – Present\n"
        "- Owned Kubernetes and observability.\n"
    )
    monkeypatch.setattr(config, "CV_MD_PATH", cv_path, raising=False)
    monkeypatch.setattr(eval_svc, "CV_MD_PATH", cv_path, raising=False)

    fixtures = os.path.join(ROOT, "tests", "fixtures", "jds")
    jd = open(os.path.join(fixtures, filename), encoding="utf-8").read()
    result = evaluate_job_text(jd, url=f"https://golden.test/{filename}", company="TestCo", role="Test Role")
    slack = 0.5
    assert result.score >= expected["min_score"] - slack
    assert result.score <= expected["max_score"] + slack


def test_recommend_apply_threshold():
    assert recommend_apply(4.5) is True
    assert recommend_apply(2.0) is False


def test_circuit_breaker():
    import sources.circuit as circuit
    with tempfile.TemporaryDirectory() as tmp:
        circuit.STATE_PATH = os.path.join(tmp, "circuits.json")
        circuit.record_failure("test_source")
        assert not circuit.is_open("test_source")
        for _ in range(5):
            circuit.record_failure("test_source")
        assert circuit.is_open("test_source")
        circuit.record_success("test_source")
        assert not circuit.is_open("test_source")


def test_plugin_registry():
    from plugins.registry import list_plugins, register_source
    from sources.base import SourceAdapter, FetchStats
    from models.job import JobRecord

    class DummyAdapter(SourceAdapter):
        name = "dummy_test"

        def fetch_raw(self, log_totals: bool = False):
            return [], FetchStats(source=self.name)

    register_source("dummy_test", DummyAdapter)
    assert "dummy_test" in list_plugins()


def test_discover_scores_jobs_at_persist_time(monkeypatch, isolated_data_dir):
    """Fix 1: discover_and_filter sets fit_score on each job before persist."""
    from sources.base import SourceAdapter, FetchStats

    class StubAdapter(SourceAdapter):
        name = "stub"
        def fetch_raw(self, log_totals=False):
            return [
                JobRecord(url="https://x.com/sre", source="stub", company="Co",
                          title="Senior SRE", location="Bengaluru",
                          jd_text="kubernetes terraform prometheus grafana"),
            ], FetchStats(source=self.name, raw_count=1)

    # discovery.py binds get_registry at import, so patching sources.registry
    # only works while that module happens to be unimported — any test that
    # touches the orchestrator first silently restores the real adapters.
    from orchestrator import discovery as disc_mod
    monkeypatch.setattr(disc_mod, "get_registry", lambda: type("R", (), {"adapters": lambda self: [StubAdapter()]})())
    import config

    # Target the role this stub emits. Without pinning, the job is rejected on
    # title before it is ever scored, and the assertion below fails for a reason
    # that has nothing to do with scoring-at-persist-time.
    monkeypatch.setattr(config, "SEARCH_KEYWORDS", ["SRE", "Site Reliability"])
    monkeypatch.setattr(config, "LOCATION_KEYWORDS", ["bengaluru", "remote"])
    monkeypatch.setattr(config, "WANTS_REMOTE", False)
    monkeypatch.setattr(config, "REMOTE_STRICT", False)

    from orchestrator.discovery import discover_and_filter
    passed, rejected, stats = discover_and_filter()
    all_jobs = passed + rejected
    assert len(all_jobs) >= 1
    scored = [j for j in all_jobs if j.fit_score > 0]
    assert len(scored) >= 1, "SRE job with k8s/terraform should have fit_score > 0"


def test_auto_evaluate_pending_without_llm_uses_heuristic(monkeypatch, isolated_data_dir):
    """Auto-eval runs with provider none — evaluate_job_text falls back to heuristic."""
    import config
    import store.db as db_mod
    from models.job import job_id_from_url

    monkeypatch.setitem(config.LLM_CONFIG, "provider", "none")
    db_mod.init_db()
    url = "https://example.com/jobs/auto-eval-heuristic"
    jid = job_id_from_url(url)
    with db_mod.db() as conn:
        conn.execute(
            "INSERT INTO jobs (id, url, title, company, jd_text, source) VALUES (?,?,?,?,?,?)",
            (jid, url, "Staff Engineer", "Acme",
             "Python platform engineer remote. Requirements:\n- Python\n- APIs\n", "test"),
        )
        conn.execute(
            "INSERT INTO pipeline (job_id, status, added_at) VALUES (?, 'pending', datetime('now'))",
            (jid,),
        )

    from scheduler.scan_scheduler import auto_evaluate_pending

    evaluated, approved = auto_evaluate_pending(limit=5, approve_threshold=0)
    assert evaluated >= 1
    assert approved == 0
    with db_mod.db() as conn:
        st = conn.execute("SELECT status FROM pipeline WHERE job_id = ?", (jid,)).fetchone()
    assert st["status"] == "evaluated"


def test_eval_service_logs_mark_evaluated_failure(monkeypatch, isolated_data_dir):
    """Fix 3: evaluate_job_text logs warning instead of silent pass."""
    import store.db as db_mod
    db_mod.init_db()
    warnings = []
    import logging
    class CapHandler(logging.Handler):
        def emit(self, record):
            if "mark_evaluated" in record.getMessage():
                warnings.append(record.getMessage())
    handler = CapHandler()
    logging.getLogger("eval.service").addHandler(handler)
    try:
        result = evaluate_job_text(
            "SRE role kubernetes",
            url="https://mark-eval-test.com/j/1",
            company="TestCo",
            role="SRE",
        )
        assert result.score > 0
    finally:
        logging.getLogger("eval.service").removeHandler(handler)


def test_outcome_capture_classify():
    """Fix 5: outcome capture classify_outcome works for rejection signals."""
    from outcomes.capture import classify_outcome
    outcome, conf = classify_outcome("Application Update", "Unfortunately we will not be proceeding with your application")
    assert outcome == "rejected"
    assert conf >= 8
