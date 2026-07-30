"""Local AI auto provider + bootstrap status."""

from __future__ import annotations

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
    import llm.local_ai as local_ai
    import llm as llm_mod

    monkeypatch.setattr(config, "DATA_DIR", tmp)
    monkeypatch.setattr(config, "PROFILE_PATH", os.path.join(tmp, "profile.yml"))
    monkeypatch.setattr(db_mod, "DATA_DIR", tmp)
    monkeypatch.setattr(db_mod, "DB_PATH", os.path.join(tmp, "shortlistr.db"))
    monkeypatch.setattr(local_ai, "_data_dir", lambda: tmp)
    # Reset LLM cache between tests
    llm_mod._cached_llm = None
    llm_mod._cache_loaded = False
    llm_mod._cached_resolved = ""
    return tmp


def test_auto_prefers_local_when_ready(isolated, monkeypatch):
    import config
    import llm as llm_mod

    config.LLM_CONFIG["provider"] = "auto"
    config.LLM_CONFIG["model"] = "qwen2.5:0.5b"
    config.LLM_CONFIG["ollama_url"] = "http://127.0.0.1:11434"

    monkeypatch.setattr("llm.local_ai.is_local_ready", lambda *a, **k: True)

    class FakeOllama:
        def __init__(self, **kw):
            self.kw = kw

        def is_available(self):
            return True

    monkeypatch.setattr("llm.ollama.OllamaProvider", FakeOllama)

    llm = llm_mod.get_llm(force_reload=True)
    assert llm is not None
    assert llm_mod.resolved_provider_name() == "ollama"


def test_auto_falls_back_to_none_without_local_or_key(isolated, monkeypatch):
    import config
    import llm as llm_mod

    config.LLM_CONFIG["provider"] = "auto"
    config.LLM_CONFIG["model"] = ""
    config.LLM_CONFIG["api_key"] = ""
    monkeypatch.setattr("llm.local_ai.is_local_ready", lambda *a, **k: False)
    monkeypatch.delenv("SHORTLISTR_LLM_API_KEY", raising=False)

    def _no_secret(name: str, default: str = "") -> str:
        return default

    monkeypatch.setattr("secrets_store.get_secret", _no_secret)

    llm = llm_mod.get_llm(force_reload=True)
    assert llm is None
    assert llm_mod.resolved_provider_name() == "none"


def test_ensure_writes_ready_status_when_model_present(isolated, monkeypatch):
    import llm.local_ai as local_ai

    monkeypatch.setattr(local_ai.shutil, "which", lambda _cmd: "/usr/bin/ollama")
    monkeypatch.setattr(local_ai, "_ollama_reachable", lambda _url: True)
    monkeypatch.setattr(local_ai, "_model_present", lambda _url, _m: True)
    monkeypatch.setattr(local_ai, "_activate_local_in_profile", lambda _m: None)

    st = local_ai.ensure_local_ai(force=True)
    assert st["ready"] is True
    assert st["phase"] == "ready"
    assert local_ai.local_ai_status()["ready"] is True


def test_activate_local_patches_profile(isolated):
    import config
    import llm.local_ai as local_ai

    path = config.PROFILE_PATH
    with open(path, "w", encoding="utf-8") as f:
        f.write(
            'candidate:\n  name: "Ada"\n\nllm:\n  provider: "none"\n  model: ""\n'
            '  api_key: ""\n  ollama_url: "http://localhost:11434"\n'
        )

    local_ai._activate_local_in_profile("qwen2.5:0.5b")
    text = open(path, encoding="utf-8").read()
    assert 'provider: "auto"' in text
    assert "qwen2.5:0.5b" in text


def test_hardware_recommends_tiny_on_low_ram(monkeypatch):
    import llm.hardware as hw

    monkeypatch.setattr(hw, "_ram_gb", lambda: 8.0)
    monkeypatch.setattr(hw, "_cpu_count", lambda: 4)
    report = hw.capability_report()
    assert report["system"]["tier"] in ("low", "mid")
    assert report["recommended_model"]
    assert any(m["recommended"] for m in report["models"])
    # 8 GB should not recommend heavy 3B as "smooth"
    heavy = next(m for m in report["models"] if m["id"] == "llama3.2:3b")
    assert heavy["fit"] in ("tight", "heavy")
    assert len(report["guide"]) >= 4


def test_hardware_high_ram_can_pick_stronger(monkeypatch):
    import llm.hardware as hw

    monkeypatch.setattr(hw, "_ram_gb", lambda: 32.0)
    monkeypatch.setattr(hw, "_cpu_count", lambda: 8)
    models = hw.recommend_models()
    pick = next(m for m in models if m["recommended"])
    assert pick["id"] in ("gemma2:2b", "llama3.2:3b", "qwen2.5:1.5b")


def test_activate_skips_cloud_provider(isolated):
    import config
    import llm.local_ai as local_ai

    path = config.PROFILE_PATH
    with open(path, "w", encoding="utf-8") as f:
        f.write('llm:\n  provider: "groq"\n  model: "llama"\n')

    local_ai._activate_local_in_profile("qwen2.5:0.5b")
    text = open(path, encoding="utf-8").read()
    assert 'provider: "groq"' in text
    assert "qwen2.5:0.5b" not in text
