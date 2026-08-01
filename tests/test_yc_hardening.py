"""YC hardening — slim /jobs list never ships full eval JSON; Windows Local AI path."""

from __future__ import annotations

import json
import os
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))


@pytest.fixture
def isolated(monkeypatch):
    tmp = tempfile.mkdtemp()
    import config
    import store.db as db_mod

    monkeypatch.setattr(config, "DATA_DIR", tmp)
    monkeypatch.setattr(config, "MIN_FIT_SCORE", 0)
    monkeypatch.setattr(db_mod, "DATA_DIR", tmp)
    monkeypatch.setattr(db_mod, "DB_PATH", os.path.join(tmp, "autojob.db"))
    return tmp


def test_fetch_jobs_slim_omits_result_json(isolated, monkeypatch):
    from api.jobs_api import fetch_jobs
    from models.job import JobRecord
    from store import db as store

    store.init_db()
    job = JobRecord(
        url="https://boards.greenhouse.io/acme/jobs/slim-1",
        source="import",
        company="Acme",
        title="Engineer",
        jd_text="Build things.",
    )
    store.upsert_job(job)
    store.add_to_pipeline(job.job_id)
    blob = json.dumps(
        {
            "score": 4.2,
            "legitimacy": "verified",
            "blocks": {"A": "x" * 500, "B": "y" * 500},
            "company": "Acme",
            "role": "Engineer",
        }
    )
    with store.db() as conn:
        conn.execute(
            "INSERT INTO eval_results (job_id, score, legitimacy, result_json, created_at) "
            "VALUES (?, 4.2, 'verified', ?, datetime('now'))",
            (job.job_id, blob),
        )
        conn.commit()
        rows = fetch_jobs(conn, status="inbox", slim=True)

    assert len(rows) == 1
    row = rows[0]
    assert "eval_result_json" not in row
    assert "result_json" not in row
    assert "eval_blocks" not in row
    # Score still present for cards
    assert row.get("eval_score") in (4.2, "4.2", 4)


def test_windows_ollama_prefers_winget_message(monkeypatch, tmp_path):
    """Without winget, Windows install message mentions download + Groq fallback."""
    import llm.local_ai as local_ai

    monkeypatch.setattr(local_ai, "_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr(local_ai.platform, "system", lambda: "Windows")
    monkeypatch.setattr(local_ai.shutil, "which", lambda _cmd: None)

    ok, msg = local_ai._install_ollama()
    assert ok is False
    assert "ollama.com" in msg.lower() or "download" in msg.lower()
    assert "Groq" in msg


def test_legacy_sources_not_in_default_adapters():
    from sources.registry import LEGACY_SOURCES, SourceRegistry

    names = {a.name for a in SourceRegistry().adapters()}
    assert not (names & LEGACY_SOURCES)
