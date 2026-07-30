"""Connections page can save credentials without rewriting the whole profile."""

from __future__ import annotations

import os
import sys
import tempfile

import pytest
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    root = tmp_path
    (root / "config").mkdir()
    (root / "automation").mkdir()
    profile = root / "config" / "profile.yml"
    profile.write_text(
        yaml.safe_dump(
            {
                "candidate": {"name": "Ada", "email": "ada@example.com"},
                "filters": {"target_titles": ["Software Engineer"]},
                "llm": {"provider": "none", "model": ""},
                "platforms": {
                    "linkedin": {"email": "li@example.com"},
                    "naukri": {"email": ""},
                },
                "sources": {"enabled": ["aggregators"]},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    import config
    import connections_store as cs
    import paths
    import secrets_store

    monkeypatch.setenv("SHORTLISTR_NO_KEYRING", "1")
    monkeypatch.setattr(config, "SHORTLISTR_ROOT", str(root))
    monkeypatch.setattr(config, "BASE_DIR", str(root / "automation"))
    monkeypatch.setattr(paths, "PROFILE_PATH", str(profile))
    monkeypatch.setattr(cs, "PROFILE_PATH", str(profile))
    monkeypatch.setattr(cs, "SHORTLISTR_ROOT", str(root))
    monkeypatch.setattr(cs, "BASE_DIR", str(root / "automation"))

    # Wipe any leftover process-env secrets from other tests.
    for name in (
        "SHORTLISTR_LINKEDIN_PASSWORD",
        "LINKEDIN_PASSWORD",
        "SHORTLISTR_NAUKRI_PASSWORD",
        "NAUKRI_PASSWORD",
        "GMAIL_APP_PASSWORD",
        "SHORTLISTR_EMAIL_PASSWORD",
        "TELEGRAM_BOT_TOKEN",
        "APIFY_TOKEN",
    ):
        os.environ.pop(name, None)

    return {"root": root, "profile": profile}


def test_get_connections_reports_flags_not_secrets(isolated):
    from connections_store import get_connections_for_ui, save_connections_from_ui

    save_connections_from_ui({"linkedin_password": "secret-li", "telegram_bot_token": "tok"})
    data = get_connections_for_ui()
    assert data["linkedin"]["password_set"] is True
    assert data["telegram"]["token_set"] is True
    blob = str(data)
    assert "secret-li" not in blob
    assert "'tok'" not in blob and '"tok"' not in blob
    assert data["linkedin"]["email"] == "li@example.com"


def test_apify_enable_adds_source_and_token(isolated):
    from connections_store import get_connections_for_ui, save_connections_from_ui
    from secrets_store import has_secret

    before = get_connections_for_ui()["apify"]
    assert before["enabled"] is False
    assert before["ready"] is False

    save_connections_from_ui({"apify_token": "apify_test_token", "apify_enabled": True})
    data = get_connections_for_ui()["apify"]
    assert data["token_set"] is True
    assert data["enabled"] is True
    assert data["ready"] is True
    assert has_secret("APIFY_TOKEN")

    written = yaml.safe_load(isolated["profile"].read_text(encoding="utf-8"))
    assert "apify" in [str(x).lower() for x in written["sources"]["enabled"]]
    assert written["sources"]["apify"]["boards"] == ["naukri", "linkedin", "indeed"]

    save_connections_from_ui({"apify_enabled": False, "apify_token": ""})
    after = get_connections_for_ui()["apify"]
    assert after["enabled"] is False
    assert after["token_set"] is False
    assert after["ready"] is False


def test_save_platform_email_preserves_sources(isolated):
    from connections_store import save_connections_from_ui

    save_connections_from_ui({"linkedin_email": "new@example.com", "naukri_email": "nk@example.com"})
    written = yaml.safe_load(isolated["profile"].read_text(encoding="utf-8"))
    assert written["platforms"]["linkedin"]["email"] == "new@example.com"
    assert written["platforms"]["naukri"]["email"] == "nk@example.com"
    assert written["sources"]["enabled"] == ["aggregators"]
    assert written["candidate"]["name"] == "Ada"


def test_clear_secret_with_empty_string(isolated):
    from connections_store import get_connections_for_ui, save_connections_from_ui
    from secrets_store import has_secret

    save_connections_from_ui({"gmail_app_password": "abcd efgh"})
    assert has_secret("GMAIL_APP_PASSWORD")
    save_connections_from_ui({"gmail_app_password": ""})
    assert not has_secret("GMAIL_APP_PASSWORD")
    assert get_connections_for_ui()["gmail"]["app_password_set"] is False


def test_mcp_servers_round_trip(isolated):
    from connections_store import get_connections_for_ui, save_connections_from_ui

    save_connections_from_ui(
        {
            "mcp_servers": [
                {
                    "name": "filesystem",
                    "type": "stdio",
                    "command": "mcp-server-filesystem",
                    "args": ["/tmp"],
                },
                {
                    "name": "api",
                    "type": "http",
                    "url": "https://example.com/mcp",
                    "secret_ref": "MY_TOKEN",
                },
            ]
        }
    )
    servers = get_connections_for_ui()["mcp_servers"]
    assert servers[0]["name"] == "filesystem"
    assert servers[0]["command"] == "mcp-server-filesystem"
    assert servers[1]["url"] == "https://example.com/mcp"


def test_profile_save_keeps_platform_emails(isolated, monkeypatch):
    """Saving the Profile page must not wipe LinkedIn/Naukri emails set on Connections."""
    import profile_store

    monkeypatch.setattr(profile_store, "PROFILE_PATH", str(isolated["profile"]))
    monkeypatch.setattr(profile_store, "ENV_FILE", str(isolated["root"] / ".env"))

    from connections_store import save_connections_from_ui
    from profile_store import save_profile_from_ui

    save_connections_from_ui(
        {"linkedin_email": "keep@example.com", "naukri_email": "nk@example.com"}
    )
    save_profile_from_ui(
        {
            "name": "Ada",
            "email": "ada@example.com",
            "target_titles": ["Software Engineer"],
            "preferred_locations": ["Remote"],
            "llm_provider": "none",
        }
    )
    written = yaml.safe_load(isolated["profile"].read_text(encoding="utf-8"))
    assert written["platforms"]["linkedin"]["email"] == "keep@example.com"
    assert written["platforms"]["naukri"]["email"] == "nk@example.com"


def test_gmail_sender_and_credentials_upload(isolated):
    from connections_store import (
        get_connections_for_ui,
        save_connections_from_ui,
        save_gmail_credentials_json,
    )

    save_connections_from_ui({"gmail_sender": "send@example.com", "gmail_app_password": "abcd efgh ijkl mnop"})
    data = get_connections_for_ui()
    assert data["gmail"]["sender"] == "send@example.com"
    assert data["gmail"]["app_password_set"] is True

    fake = {
        "installed": {
            "client_id": "123.apps.googleusercontent.com",
            "client_secret": "secret",
            "redirect_uris": ["http://localhost"],
        }
    }
    import json

    out = save_gmail_credentials_json(json.dumps(fake).encode())
    assert out["gmail"]["credentials_present"] is True


def test_bad_gmail_credentials_rejected(isolated):
    from connections_store import save_gmail_credentials_json

    import pytest

    with pytest.raises(ValueError, match="not valid JSON"):
        save_gmail_credentials_json(b"not-json")
    with pytest.raises(ValueError, match="OAuth client"):
        save_gmail_credentials_json(b'{"foo": 1}')


def test_connections_api_endpoints(isolated, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    import connections_store as cs
    import profile_store

    monkeypatch.setattr(profile_store, "PROFILE_PATH", str(isolated["profile"]))
    monkeypatch.setattr(cs, "PROFILE_PATH", str(isolated["profile"]))

    from api.main import create_app

    client = TestClient(create_app())
    before = client.get("/setup/connections").json()
    assert before["linkedin"]["email"] == "li@example.com"

    after = client.put(
        "/setup/connections",
        json={"linkedin_email": "api@example.com", "telegram_bot_token": "bot-tok"},
    ).json()
    assert after["linkedin"]["email"] == "api@example.com"
    assert after["telegram"]["token_set"] is True
