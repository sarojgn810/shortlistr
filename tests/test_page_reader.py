"""Optional page-reader scrape boost."""

from __future__ import annotations

import os
import sys

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

    monkeypatch.setenv("SHORTLISTR_NO_KEYRING", "1")
    monkeypatch.delenv("SHORTLISTR_PAGE_READER", raising=False)
    monkeypatch.delenv("SHORTLISTR_AGENT_REACH", raising=False)
    monkeypatch.setattr(config, "SHORTLISTR_ROOT", str(root))
    monkeypatch.setattr(config, "BASE_DIR", str(root / "automation"))
    monkeypatch.setattr(paths, "PROFILE_PATH", str(profile))
    monkeypatch.setattr(cs, "PROFILE_PATH", str(profile))
    monkeypatch.setattr(cs, "SHORTLISTR_ROOT", str(root))
    monkeypatch.setattr(cs, "BASE_DIR", str(root / "automation"))

    return {"root": root, "profile": profile}


def test_page_reader_disabled_by_default(monkeypatch, tmp_path):
    from scrapers import page_reader

    monkeypatch.delenv("SHORTLISTR_PAGE_READER", raising=False)
    monkeypatch.delenv("SHORTLISTR_AGENT_REACH", raising=False)
    profile = tmp_path / "profile.yml"
    profile.write_text("sources:\n  enabled: []\n", encoding="utf-8")
    monkeypatch.setattr("paths.PROFILE_PATH", str(profile))
    assert page_reader.is_enabled() is False


def test_page_reader_enabled_via_env(monkeypatch):
    from scrapers import page_reader

    monkeypatch.setenv("SHORTLISTR_PAGE_READER", "1")
    assert page_reader.is_enabled() is True


def test_page_reader_enabled_via_profile(monkeypatch, tmp_path):
    from scrapers import page_reader

    monkeypatch.delenv("SHORTLISTR_PAGE_READER", raising=False)
    monkeypatch.delenv("SHORTLISTR_AGENT_REACH", raising=False)
    profile = tmp_path / "profile.yml"
    profile.write_text(
        "sources:\n  page_reader:\n    enabled: true\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("paths.PROFILE_PATH", str(profile))
    assert page_reader.is_enabled() is True


def test_page_reader_reads_legacy_agent_reach_key(monkeypatch, tmp_path):
    from scrapers import page_reader

    monkeypatch.delenv("SHORTLISTR_PAGE_READER", raising=False)
    monkeypatch.delenv("SHORTLISTR_AGENT_REACH", raising=False)
    profile = tmp_path / "profile.yml"
    profile.write_text(
        "sources:\n  agent_reach:\n    enabled: true\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("paths.PROFILE_PATH", str(profile))
    assert page_reader.is_enabled() is True


def test_markdown_as_html_escapes():
    from scrapers.page_reader import markdown_as_html

    html = markdown_as_html("Hello <script>alert(1)</script>")
    assert "<script>" not in html
    assert "Hello" in html
    assert "page-reader" in html


def test_fetch_page_uses_reader_when_spa_empty(monkeypatch):
    from scrapers import browser_fetch
    from scrapers.browser_fetch import PageFetch

    monkeypatch.setattr(browser_fetch, "_from_cache", lambda *a, **k: None)
    monkeypatch.setattr(
        browser_fetch,
        "_fetch_requests",
        lambda url, timeout: PageFetch(
            url=url,
            html="<html><body><div id='__next'></div></body></html>",
            status=200,
            via="requests",
        ),
    )
    monkeypatch.setattr(
        browser_fetch,
        "_fetch_playwright",
        lambda url: PageFetch(url=url, error="should not run", via="playwright"),
    )

    def fake_reader(url, timeout=25):
        return ("# Role\n\nStaff SRE at Example Corp\n\n" + ("requirements " * 20), "")

    monkeypatch.setattr("scrapers.page_reader.fetch_via_reader", fake_reader)
    monkeypatch.setattr("scrapers.page_reader.is_enabled", lambda: True)
    monkeypatch.setattr(browser_fetch, "_store_cache", lambda *a, **k: None)

    page = browser_fetch.fetch_page("https://example.com/jobs/1", allow_browser=True)
    assert page.via == "page_reader"
    assert "Staff SRE" in page.html


def test_fetch_page_skips_reader_when_disabled(monkeypatch):
    from scrapers import browser_fetch
    from scrapers.browser_fetch import PageFetch

    monkeypatch.setattr(browser_fetch, "_from_cache", lambda *a, **k: None)
    monkeypatch.setattr(
        browser_fetch,
        "_fetch_requests",
        lambda url, timeout: PageFetch(
            url=url,
            html="<html><body><div id='__next'></div></body></html>",
            status=200,
            via="requests",
        ),
    )
    monkeypatch.setattr(
        browser_fetch,
        "_fetch_playwright",
        lambda url: PageFetch(
            url=url,
            html="<html><body>" + ("job description " * 50) + "</body></html>",
            status=200,
            via="playwright",
        ),
    )
    monkeypatch.setattr("scrapers.page_reader.is_enabled", lambda: False)
    monkeypatch.setattr(browser_fetch, "_store_cache", lambda *a, **k: None)

    page = browser_fetch.fetch_page("https://example.com/jobs/1", allow_browser=True)
    assert page.via == "playwright"


def test_connections_page_reader_toggle(isolated):
    from connections_store import get_connections_for_ui, save_connections_from_ui

    before = get_connections_for_ui()["page_reader"]
    assert before["enabled"] is False

    save_connections_from_ui({"page_reader_enabled": True})
    after = get_connections_for_ui()["page_reader"]
    assert after["enabled"] is True
    assert after["ready"] is True

    save_connections_from_ui({"page_reader_enabled": False})
    off = get_connections_for_ui()["page_reader"]
    assert off["enabled"] is False
