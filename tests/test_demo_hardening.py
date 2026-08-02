"""Demo hardening — slim /jobs list never ships full eval JSON; Windows Local AI path."""

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
    monkeypatch.setattr(db_mod, "DB_PATH", os.path.join(tmp, "shortlistr.db"))
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


def test_coerce_cloud_model_drops_ollama_tags():
    from llm import coerce_cloud_model
    from llm.groq_llm import DEFAULT_MODEL

    assert coerce_cloud_model("groq", "qwen2.5:0.5b") == DEFAULT_MODEL
    assert coerce_cloud_model("groq", "llama-3.3-70b-versatile") == "llama-3.3-70b-versatile"
    assert coerce_cloud_model("ollama", "qwen2.5:0.5b") == "qwen2.5:0.5b"
    assert coerce_cloud_model("auto", "qwen2.5:0.5b") == "qwen2.5:0.5b"


def test_build_cloud_persists_coerced_groq_model(tmp_path, monkeypatch):
    """Leftover Ollama tags must be rewritten in profile.yml, not only in memory."""
    import llm as llm_mod
    from llm.groq_llm import DEFAULT_MODEL

    profile = tmp_path / "profile.yml"
    profile.write_text(
        'llm:\n  provider: "groq"\n  model: "qwen2.5:0.5b"\n  ollama_url: "http://localhost:11434"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr("config.PROFILE_PATH", str(profile), raising=False)
    import config as cfg

    monkeypatch.setattr(cfg, "PROFILE_PATH", str(profile), raising=False)
    cfg.LLM_CONFIG["provider"] = "groq"
    cfg.LLM_CONFIG["model"] = "qwen2.5:0.5b"

    provider = llm_mod._build_cloud("groq", "gsk_test_key", "qwen2.5:0.5b")
    assert provider is not None
    assert provider.model == DEFAULT_MODEL
    text = profile.read_text(encoding="utf-8")
    assert "qwen2.5:0.5b" not in text
    assert DEFAULT_MODEL in text


def test_groq_complete_swaps_ollama_tag(monkeypatch):
    from llm.groq_llm import DEFAULT_MODEL, GroqProvider

    calls = []

    class _FakeCompletions:
        def create(self, **kwargs):
            calls.append(kwargs["model"])

            class _Msg:
                content = "ok"

            class _Choice:
                message = _Msg()

            class _Resp:
                choices = [_Choice()]

            return _Resp()

    class _FakeClient:
        chat = type("C", (), {"completions": _FakeCompletions()})()

    p = GroqProvider(api_key="gsk_x", model="qwen2.5:0.5b")
    monkeypatch.setattr(p, "_get_client", lambda: _FakeClient())
    assert p.complete("hi") == "ok"
    assert calls == [DEFAULT_MODEL]
    assert p.model == DEFAULT_MODEL


def test_strip_ansi_from_local_ai_status(tmp_path, monkeypatch):
    import llm.local_ai as local_ai

    monkeypatch.setattr(local_ai, "_data_dir", lambda: str(tmp_path))
    dirty = '\x1b[?25l\x1b[1Gpulling manifest \x1b[K\nError: proxyconnect tcp'
    local_ai._write_status(phase="error", error=dirty, message=dirty)
    st = local_ai.local_ai_status()
    assert "\x1b" not in (st.get("error") or "")
    assert "pulling manifest" in (st.get("error") or "")


def test_automation_min_score_legacy_remap(isolated):
    from store import db as store
    from store.settings import get_automation_settings, set_automation_settings

    store.init_db()
    set_automation_settings({"auto_evaluate_min_score": 4.0})
    s = get_automation_settings()
    assert s["auto_evaluate_min_score"] == 40
    set_automation_settings({"auto_evaluate_min_score": 55})
    assert get_automation_settings()["auto_evaluate_min_score"] == 55


def test_legacy_sources_not_in_default_adapters():
    from sources.registry import LEGACY_SOURCES, SourceRegistry

    names = {a.name for a in SourceRegistry().adapters()}
    assert not (names & LEGACY_SOURCES)
