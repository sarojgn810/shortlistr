"""J1 Judgment MVP tests — status machine, receipts, explain, diff."""

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


def _seed_job(isolated_data_dir, url: str = "https://boards.greenhouse.io/acme/jobs/j1-test-1"):
    from models.job import JobRecord, job_id_from_url
    from store import db as store

    job_id = job_id_from_url(url)
    store.init_db()
    job = JobRecord(
        url=url,
        source="greenhouse",
        company="Acme",
        title="SRE",
        location="Remote",
        jd_text="Build reliable systems.",
        job_id=job_id,
        fit_score=72,
        fit_reason="Strong platform fit; remote aligns.",
    )
    store.upsert_job(job)
    store.add_to_pipeline(job_id, "pending")
    return job_id


def test_schema_v2_migration(isolated_data_dir):
    from store import db as store

    store.init_db()
    with store.db() as conn:
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "application_receipts" in tables
        ver = conn.execute("SELECT version FROM schema_version").fetchone()["version"]
        assert ver >= 2


def test_pipeline_transitions(isolated_data_dir):
    from store.status import (
        StatusError,
        mark_approved,
        mark_evaluated,
        mark_skipped,
        mark_submitted,
        pipeline_status_counts,
    )

    jid = _seed_job(isolated_data_dir)
    mark_evaluated(jid, company="Acme", role="SRE", score=4.2)
    mark_approved(jid)
    app_id = mark_submitted(jid, company="Acme", role="SRE", score=4.2)

    counts = pipeline_status_counts()
    assert counts["submitted"] == 1
    assert app_id > 0

    with pytest.raises(StatusError):
        mark_skipped(jid)


def test_skip_then_reconsider_then_submit(isolated_data_dir):
    """A skipped job that is un-skipped must be able to re-enter the flow.

    Regression: mark_skipped() set the application row to the terminal 'skip'
    state, so after un-skipping the pipeline, the next upsert (skip → evaluated
    / applied) raised StatusError and blocked re-submission.
    """
    from store.status import (
        get_pipeline_row,
        mark_approved,
        mark_evaluated,
        mark_skipped,
        mark_submitted,
        transition_pipeline,
    )

    jid = _seed_job(isolated_data_dir)
    mark_evaluated(jid, company="Acme", role="SRE", score=4.2)
    mark_skipped(jid)
    assert get_pipeline_row(jid)["status"] == "skipped"

    # Reconsider: un-skip → re-evaluate → approve → submit.
    transition_pipeline(jid, "pending", reason="user_undo")
    mark_evaluated(jid, company="Acme", role="SRE", score=4.2)
    mark_approved(jid)
    app_id = mark_submitted(jid, company="Acme", role="SRE", score=4.2)

    assert app_id > 0
    assert get_pipeline_row(jid)["status"] == "submitted"


def test_invalid_pipeline_transition(isolated_data_dir):
    from store.status import StatusError, transition_pipeline

    jid = _seed_job(isolated_data_dir)
    with pytest.raises(StatusError):
        transition_pipeline(jid, "approved")


def test_approve_straight_from_inbox(isolated_data_dir):
    """Approving a not-yet-evaluated job must work.

    Regression: the inbox Approve button hit `pending → approved`, which is not a
    legal single hop, so the API returned 400 "Could not approve".
    """
    from store.status import get_pipeline_row, mark_approved

    jid = _seed_job(isolated_data_dir)
    assert get_pipeline_row(jid)["status"] == "pending"

    mark_approved(jid)
    assert get_pipeline_row(jid)["status"] == "approved"


def test_submit_a_previously_skipped_job(isolated_data_dir):
    """Submitting a skipped job must move the pipeline row too.

    Regression: the transition was silently skipped, leaving pipeline='skipped'
    with application='applied' — and `fetch_tracker_board` filters skipped rows
    out, so the submitted job vanished from the board.
    """
    from store.status import get_pipeline_row, mark_evaluated, mark_skipped, mark_submitted

    jid = _seed_job(isolated_data_dir)
    mark_evaluated(jid, company="Acme", role="SRE", score=4.2)
    mark_skipped(jid)

    app_id = mark_submitted(jid, company="Acme", role="SRE", score=4.2)
    assert app_id > 0
    assert get_pipeline_row(jid)["status"] == "submitted"


def test_reevaluating_a_skipped_job_revives_it(isolated_data_dir):
    from store.status import get_pipeline_row, mark_evaluated, mark_skipped

    jid = _seed_job(isolated_data_dir)
    mark_evaluated(jid, company="Acme", role="SRE", score=4.0)
    mark_skipped(jid)

    mark_evaluated(jid, company="Acme", role="SRE", score=4.6)
    assert get_pipeline_row(jid)["status"] == "evaluated"


def test_skipping_twice_is_idempotent(isolated_data_dir):
    from store.status import get_pipeline_row, mark_evaluated, mark_skipped

    jid = _seed_job(isolated_data_dir)
    mark_evaluated(jid, company="Acme", role="SRE", score=4.0)
    mark_skipped(jid)
    mark_skipped(jid)
    assert get_pipeline_row(jid)["status"] == "skipped"


def test_invalid_job_id_rejected(isolated_data_dir):
    from store.status import StatusError, validate_job_id

    with pytest.raises(StatusError):
        validate_job_id("../etc/passwd")
    with pytest.raises(StatusError):
        validate_job_id("short")


def test_application_receipt_create(isolated_data_dir):
    from store.receipts import ReceiptError, create_receipt, list_receipts_for_job

    jid = _seed_job(isolated_data_dir)
    rid = create_receipt(
        jid,
        "prep",
        fields={
            "to_email": "hiring@acme.com",
            "subject": "Application",
            "api_token": "secret-should-drop",
        },
        resume_path="output/Acme.pdf",
        cover_letter_text="Hello team",
    )
    assert rid > 0
    receipts = list_receipts_for_job(jid)
    assert len(receipts) == 1
    assert receipts[0]["fields"].get("api_token") is None
    assert receipts[0]["channel"] == "prep"

    with pytest.raises(ReceiptError):
        create_receipt(jid, "bogus", fields={})


def test_receipt_rejects_invalid_email(isolated_data_dir):
    from store.receipts import ReceiptError, create_receipt

    jid = _seed_job(isolated_data_dir)
    with pytest.raises(ReceiptError):
        create_receipt(jid, "email", fields={"to_email": "not-an-email"})


def test_receipt_rejects_path_traversal(isolated_data_dir):
    from store.receipts import ReceiptError, create_receipt

    jid = _seed_job(isolated_data_dir)
    with pytest.raises(ReceiptError):
        create_receipt(jid, "prep", fields={}, resume_path="../../../etc/passwd")


def test_explain_combines_fit_and_eval(isolated_data_dir):
    from eval.explain import explain_job, format_explain_text
    from store import db as store
    from store.status import mark_evaluated

    jid = _seed_job(isolated_data_dir)
    mark_evaluated(jid, company="Acme", role="SRE", score=4.1)

    with store.db() as conn:
        conn.execute(
            """
            INSERT INTO eval_results (job_id, schema_version, score, legitimacy, result_json)
            VALUES (?, 'v1', ?, ?, ?)
            """,
            (
                jid,
                4.1,
                "verified",
                json.dumps(
                    {
                        "blocks": {
                            "B": "Platform SRE match. Remote OK. Strong K8s overlap.",
                        }
                    }
                ),
            ),
        )

    data = explain_job(jid)
    assert data["eval_score"] == 4.1
    assert data["fit_score"] == 72
    assert data["legitimacy"] == "verified"
    assert len(data["bullets"]) >= 1
    text = format_explain_text(data)
    assert "Acme" in text
    assert "Why matched" in text


def test_diff_detects_tailored_header(isolated_data_dir, monkeypatch):
    from prep.diff import build_tailored_text, compute_diff, format_diff_text
    import config

    cv_path = os.path.join(isolated_data_dir, "cv.md")
    open(cv_path, "w", encoding="utf-8").write("# Jane Doe\n\n## Summary\nSRE leader.\n")
    monkeypatch.setattr(config, "CV_MD_PATH", cv_path)

    jid = _seed_job(isolated_data_dir)
    job = {"company": "Acme", "title": "SRE"}
    tailored = build_tailored_text(job)
    assert "Applying for" in tailored

    diff = compute_diff(jid)
    assert diff["change_count"] >= 1
    out = format_diff_text(diff)
    assert "change" in out.lower()


def test_eval_service_marks_pipeline_evaluated(isolated_data_dir, monkeypatch):
    from eval.service import evaluate_job_text
    from store.status import get_pipeline_row

    url = "https://boards.greenhouse.io/acme/jobs/j1-eval-test"
    jid = _seed_job(isolated_data_dir, url)
    evaluate_job_text(
        "Senior SRE role with Kubernetes.",
        url=url,
        company="Acme",
        role="SRE",
    )
    row = get_pipeline_row(jid)
    assert row is not None
    assert row["status"] == "evaluated"


class _FakeProvider:
    def __init__(self, response: str):
        self._response = response

    def is_available(self) -> bool:
        return True

    def complete(self, *args, **kwargs) -> str:
        return self._response


def test_eval_falls_back_when_llm_returns_empty(isolated_data_dir, monkeypatch):
    """A parseable-but-empty LLM payload must drop to template mode, not pose as a real eval."""
    import eval.service as eval_service

    monkeypatch.setattr(eval_service, "get_llm", lambda: _FakeProvider("{}"))
    url = "https://boards.greenhouse.io/acme/jobs/j1-empty-llm"
    _seed_job(isolated_data_dir, url)
    result = eval_service.evaluate_job_text(
        "Senior SRE role with Kubernetes and Terraform.",
        url=url,
        company="Acme",
        role="SRE",
    )
    assert result.eval_mode == "template"
    assert result.score > 0  # heuristic produced a real score, not a bare 0.0


def test_eval_safe_score_parse_keeps_llm_mode(isolated_data_dir, monkeypatch):
    """A non-numeric score must not 500; a response with real blocks stays llm mode."""
    import eval.service as eval_service

    monkeypatch.setattr(
        eval_service,
        "get_llm",
        lambda: _FakeProvider('{"score": "N/A", "blocks": {"A": "Real A-G analysis."}}'),
    )
    url = "https://boards.greenhouse.io/acme/jobs/j1-bad-score"
    _seed_job(isolated_data_dir, url)
    result = eval_service.evaluate_job_text("SRE role.", url=url, company="Acme", role="SRE")
    assert result.eval_mode == "llm"
    assert result.score == 0.0


def test_api_pipeline_status_requires_valid_job(isolated_data_dir):
    pytest.importorskip("fastapi")
    from api.main import create_app
    from fastapi.testclient import TestClient

    _seed_job(isolated_data_dir, "https://boards.greenhouse.io/acme/jobs/j1-api-1")
    client = TestClient(create_app())
    r = client.post("/jobs/zzzzzzzzzzzzzzzz/pipeline-status", json={"status": "approved"})
    assert r.status_code == 400


def test_api_explain_endpoint(isolated_data_dir):
    pytest.importorskip("fastapi")
    from api.main import create_app
    from fastapi.testclient import TestClient
    from store.status import mark_evaluated

    jid = _seed_job(isolated_data_dir, "https://boards.greenhouse.io/acme/jobs/j1-explain-1")
    mark_evaluated(jid, company="Acme", role="SRE", score=3.9)
    client = TestClient(create_app())
    r = client.get(f"/jobs/{jid}/explain")
    assert r.status_code == 200
    body = r.json()
    assert body["job_id"] == jid
    assert "bullets" in body
