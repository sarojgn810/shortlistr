"""Bootstrap seed + web profile setup API."""

from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))


def test_seed_local_files_idempotent(tmp_path, monkeypatch):
    import config
    from bootstrap.seed import seed_local_files

    monkeypatch.setattr(config, "SHORTLISTR_ROOT", str(tmp_path))
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path / "data"))

    import bootstrap.seed as seed_mod
    import paths
    import profile_store

    monkeypatch.setattr(seed_mod, "SHORTLISTR_ROOT", str(tmp_path))
    monkeypatch.setattr(seed_mod, "DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(seed_mod, "CV_MD_PATH", str(tmp_path / "cv.md"))
    monkeypatch.setattr(paths, "SHORTLISTR_ROOT", str(tmp_path))
    monkeypatch.setattr(paths, "DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(paths, "PORTALS_PATH", str(tmp_path / "portals.yml"))
    monkeypatch.setattr(paths, "PROFILE_PATH", str(tmp_path / "config" / "profile.yml"))
    monkeypatch.setattr(config, "CV_MD_PATH", str(tmp_path / "cv.md"))
    monkeypatch.setattr(profile_store, "PROFILE_PATH", str(tmp_path / "config" / "profile.yml"))
    monkeypatch.setattr(profile_store, "SHORTLISTR_ROOT", str(tmp_path))

    os.makedirs(tmp_path / "templates", exist_ok=True)
    os.makedirs(tmp_path / "config", exist_ok=True)
    os.makedirs(tmp_path / "modes", exist_ok=True)
    open(tmp_path / "templates" / "portals.example.yml", "w").write("companies: []\n")
    open(tmp_path / ".env.example", "w").write("SHORTLISTR_LLM_API_KEY=\n")
    open(tmp_path / "modes" / "_profile.template.md", "w").write("# profile\n")
    open(tmp_path / "templates" / "applications.example.md", "w").write("# Applications\n")

    first = seed_local_files()
    second = seed_local_files()
    assert len(first) >= 4
    assert second == []
    assert os.path.isfile(tmp_path / "portals.yml")
    assert os.path.isfile(tmp_path / ".env")
    assert os.path.isfile(tmp_path / "cv.md")
    # Profile is created in onboarding from the user's résumé — not seeded.
    assert not os.path.isfile(tmp_path / "config" / "profile.yml")
    cv = open(tmp_path / "cv.md").read().lower()
    assert "your name" in cv
    assert "email@example.com" in cv


def test_profile_store_roundtrip(tmp_path, monkeypatch):
    import config
    from profile_store import get_profile_for_ui, save_profile_from_ui

    monkeypatch.setattr(config, "SHORTLISTR_ROOT", str(tmp_path))

    import paths
    import profile_store

    profile_path = tmp_path / "config" / "profile.yml"
    env_path = tmp_path / ".env"
    monkeypatch.setattr(paths, "PROFILE_PATH", str(profile_path))
    monkeypatch.setattr(profile_store, "PROFILE_PATH", str(profile_path))
    monkeypatch.setattr(profile_store, "ENV_FILE", str(env_path))
    monkeypatch.setattr(profile_store, "SHORTLISTR_ROOT", str(tmp_path))

    os.makedirs(tmp_path / "config", exist_ok=True)
    open(tmp_path / ".env.example", "w").write("SHORTLISTR_LLM_API_KEY=\n")

    payload = {
        "name": "Alex Candidate",
        "email": "alex@example.com",
        "phone": "+1 555 0100",
        "location": "Remote",
        "linkedin": "https://linkedin.com/in/alex-candidate",
        "github": "",
        "years_exp": 5,
        "min_salary_inr_lpa": 0,
        "min_salary_usd": 0,
        "target_titles": ["Software Engineer", "Backend Engineer"],
        "llm_provider": "openai",
        "llm_model": "gpt-4o",
        "llm_api_key": "sk-test-key",
    }
    saved = save_profile_from_ui(payload)
    assert saved["name"] == "Alex Candidate"
    assert saved["llm_api_key_set"] is True
    assert "Software Engineer" in saved["target_titles"]

    again = get_profile_for_ui()
    assert again["email"] == "alex@example.com"
    assert os.path.isfile(profile_path)
    # The LLM key is stored in the secret store (keychain in prod; process env
    # under pytest), never plaintext in profile.yml.
    import secrets_store

    assert secrets_store.get_secret("SHORTLISTR_LLM_API_KEY") == "sk-test-key"
    assert "sk-test-key" not in open(profile_path).read()


def test_profile_api_endpoints(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    import config
    from api.main import create_app
    from fastapi.testclient import TestClient

    monkeypatch.setattr(config, "SHORTLISTR_ROOT", str(tmp_path))
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path / "data"))
    os.makedirs(tmp_path / "data", exist_ok=True)
    os.makedirs(tmp_path / "config", exist_ok=True)
    open(tmp_path / ".env.example", "w").write("SHORTLISTR_LLM_API_KEY=\n")

    import paths
    import profile_store

    profile_path = tmp_path / "config" / "profile.yml"
    env_path = tmp_path / ".env"
    monkeypatch.setattr(paths, "PROFILE_PATH", str(profile_path))
    monkeypatch.setattr(profile_store, "PROFILE_PATH", str(profile_path))
    monkeypatch.setattr(profile_store, "ENV_FILE", str(env_path))
    monkeypatch.setattr(profile_store, "SHORTLISTR_ROOT", str(tmp_path))

    client = TestClient(create_app())
    r = client.get("/setup/profile")
    assert r.status_code == 200
    assert r.json()["exists"] is False

    r2 = client.put(
        "/setup/profile",
        json={
            "name": "Test User",
            "email": "test@example.com",
            "target_titles": ["SRE"],
            "llm_provider": "none",
        },
    )
    assert r2.status_code == 200
    assert r2.json()["exists"] is True
