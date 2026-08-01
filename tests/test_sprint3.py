"""Sprint 3 — apply assist, email routing, agent API, legacy defaults."""

from __future__ import annotations

import os
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))


@pytest.fixture
def isolated_data_dir(monkeypatch):
    tmp = tempfile.mkdtemp()
    import config

    monkeypatch.setattr(config, "DATA_DIR", tmp)
    import store.db as db_mod

    monkeypatch.setattr(db_mod, "DATA_DIR", tmp)
    monkeypatch.setattr(db_mod, "DB_PATH", os.path.join(tmp, "shortlistr.db"))
    return tmp


def test_mcp_manifest_lists_core_tools():
    from connectors.manifest import list_tools

    names = {t["name"] for t in list_tools()}
    assert "shortlistr.evaluate" in names
    assert "shortlistr.apply_assist" in names
    assert "shortlistr.queue_apply" in names


def test_legacy_scrapers_disabled_by_default():
    import config

    # Workday is a first-class portals.yml adapter — not legacy-disabled.
    assert "workday" not in config.DISABLED_LEGACY_SOURCES
    assert "workday" in config.SOURCE_ENABLED
    assert "monster" in config.DISABLED_LEGACY_SOURCES


def test_enqueue_task(isolated_data_dir):
    from store import db as store

    store.init_db()
    tid = store.enqueue_task("discover", {"dry_run": True})
    assert tid > 0


def test_email_routing_classify():
    from processors.email_routing import route_recruiter_message

    r = route_recruiter_message(
        sender="recruiter@acmecorp.com",
        subject="Interview schedule for SRE role",
        body="Let's schedule your technical interview next week.",
        dry_run=True,
    )
    assert r is None or r.get("to_status") == "interview"


def test_email_routing_updates_application(isolated_data_dir):
    from processors.email_routing import route_recruiter_message
    from store import db as store

    store.init_db()
    with store.db() as conn:
        conn.execute(
            """
            INSERT INTO applications (company, role, score, status)
            VALUES ('Acme Corp', 'SRE', 4.2, 'applied')
            """
        )

    r = route_recruiter_message(
        sender="hr@acmecorp.com",
        subject="Next steps",
        body="Thank you for applying. We would like to speak with you.",
        dry_run=False,
    )
    assert r is not None
    assert r.get("applied") is True
    assert r.get("to_status") == "responded"


def test_apply_assist_requires_approved_pipeline(isolated_data_dir):
    from apply.ats_fill import apply_assist_for_job
    from models.job import JobRecord
    from store import db as store
    from store.status import StatusError

    store.init_db()
    job = JobRecord(
        url="https://boards.greenhouse.io/acme/jobs/1",
        source="test",
        company="Acme",
        title="SRE",
    )
    store.upsert_job(job)
    store.add_to_pipeline(job.job_id)
    with pytest.raises(StatusError):
        apply_assist_for_job(job.job_id)


def test_golden_jd_file_bands(monkeypatch):
    import json
    import config
    from eval.service import evaluate_job_text

    # The heuristic scores a title-family hit off the live profile. Pin the
    # targeting these fixtures were written for — reading the developer's own
    # profile.yml made the bands pass here and fail on a fresh clone, which has
    # no profile at all.
    monkeypatch.setattr(
        config,
        "SEARCH_KEYWORDS",
        ["site reliability engineer", "sre", "devops engineer", "platform engineer"],
    )

    fixture_dir = os.path.join(ROOT, "tests", "fixtures", "jds")
    expected = json.load(open(os.path.join(fixture_dir, "expected.json"), encoding="utf-8"))
    for filename, bands in expected.items():
        jd = open(os.path.join(fixture_dir, filename), encoding="utf-8").read()
        result = evaluate_job_text(jd, url=f"https://golden.test/{filename}", company="Test", role="Role")
        slack = 0.5
        assert result.score >= bands["min_score"] - slack, filename
        assert result.score <= bands["max_score"] + slack, filename


def test_fill_form_invalid_url():
    from apply.ats_fill import fill_application_form

    report = fill_application_form("not-a-url")
    assert report["errors"]
