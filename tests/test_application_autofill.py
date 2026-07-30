"""Application Auto-Fill → Chromium form fill (no submit).

Pins the profile → Playwright path: new Auto-Fill fields land on a local ATS
fixture, and profile.yml changes are live without an API restart.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))

FIXTURE = Path(__file__).parent / "fixtures" / "ats_apply_form.html"

PROFILE = {
    "first_name": "Alex",
    "last_name": "Candidate",
    "full_name": "Alex Candidate",
    "preferred_name": "Alex",
    "email": "alex@example.com",
    "phone": "+1 555 010 1234",
    "linkedin": "https://linkedin.com/in/alex-candidate",
    "github": "https://github.com/alex-candidate",
    "website": "https://www.example.com",
    "location": "Seattle, USA",
    "years_exp": "5",
    "notice_period": "30 Days",
    "current_ctc": "120k USD",
    "expected_ctc": "150k USD",
    "how_heard": "LinkedIn",
    "work_authorization": "Authorized to work; no sponsorship required",
    "willing_to_relocate": "Open to discussion",
    "cover_letter_snippet": "Software engineer focused on reliable platforms.",
}


@pytest.fixture
def isolated_profile(monkeypatch, tmp_path):
    """Write a temp profile.yml and point config/profile_store at it."""
    import yaml

    import config as cfg
    import profile_store as ps
    import store.db as db_mod

    profile = {
        "candidate": {
            "name": "Alex Candidate",
            "email": "alex@example.com",
            "phone": "+1 555 010 1234",
            "location": "Seattle, USA",
            "linkedin": "https://linkedin.com/in/alex-candidate",
            "github": "https://github.com/alex-candidate",
            "years_exp": 5,
        },
        "filters": {
            "target_titles": ["Software Engineer"],
            "preferred_locations": ["Seattle", "Remote"],
            "min_salary_inr_lpa": 0,
            "min_salary_usd": 0,
            "salary_unlisted": "include",
            "deal_breakers": [],
        },
        "application": {
            "website": "https://www.example.com",
            "notice_period": "30 Days",
            "current_ctc": "120k USD",
            "expected_ctc": "150k USD",
            "how_heard": "LinkedIn",
            "work_authorization": "Authorized to work; no sponsorship required",
            "preferred_name": "Alex",
            "cover_letter_snippet": "Software engineer focused on reliable platforms.",
            "willing_to_relocate": "Open to discussion",
        },
        "llm": {"provider": "none", "model": ""},
        "scoring": {"min_fit_score": 40},
        "sources": {"enabled": ["aggregators"], "apify": {"boards": ["naukri"]}},
    }
    path_dir = tmp_path / "config"
    path_dir.mkdir()
    path = path_dir / "profile.yml"
    path.write_text(yaml.safe_dump(profile, sort_keys=False), encoding="utf-8")

    monkeypatch.setattr(cfg, "SHORTLISTR_ROOT", str(tmp_path))
    monkeypatch.setattr(ps, "PROFILE_PATH", str(path))
    monkeypatch.setattr(db_mod, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(db_mod, "DB_PATH", str(tmp_path / "shortlistr.db"))
    cfg.reload_discovery_config()
    return path


def test_profile_fields_include_new_autofill_keys(isolated_profile):
    from apply.ats_fill import _profile_fields

    fields = _profile_fields()
    assert fields["work_authorization"].startswith("Authorized")
    assert fields["preferred_name"] == "Alex"
    assert "reliable platforms" in fields["cover_letter_snippet"]
    assert fields["willing_to_relocate"] == "Open to discussion"
    assert fields["website"] == "https://www.example.com"


def test_save_preserves_sources_and_reloads_application(isolated_profile):
    import config as cfg
    import profile_store as ps
    import yaml

    ui = ps.get_profile_for_ui()
    ui["work_authorization"] = "US work auth; H1B transfer OK"
    ui["cover_letter_snippet"] = "Short updated blurb."
    saved = ps.save_profile_from_ui(ui)

    assert saved["work_authorization"].startswith("US work")
    assert "updated blurb" in saved["cover_letter_snippet"]

    data = yaml.safe_load(isolated_profile.read_text(encoding="utf-8"))
    assert data["sources"]["enabled"] == ["aggregators"]
    assert data["sources"]["apify"]["boards"] == ["naukri"]
    assert cfg.APPLICATION["work_authorization"].startswith("US work")


def test_chromium_fills_ats_fixture_from_profile():
    from apply.ats_fill import _fill_by_labels, _fill_known_fields, playwright_ready

    ok, msg = playwright_ready()
    if not ok:
        pytest.skip(msg)

    from playwright.sync_api import sync_playwright

    url = FIXTURE.resolve().as_uri()
    report: dict = {"filled": [], "unfilled": []}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="domcontentloaded")
        _fill_known_fields(page, PROFILE, report)
        _fill_by_labels(page, PROFILE, report)

        assert page.input_value("#email") == PROFILE["email"]
        assert page.input_value("#phone") == PROFILE["phone"]
        assert page.input_value("#linkedin") == PROFILE["linkedin"]
        assert page.input_value("#website") == PROFILE["website"]
        assert page.input_value("#notice") == PROFILE["notice_period"]
        assert page.input_value("#current_ctc") == PROFILE["current_ctc"]
        assert page.input_value("#expected_ctc") == PROFILE["expected_ctc"]
        assert page.input_value("#how_heard") == PROFILE["how_heard"]
        assert page.input_value("#work_auth") == PROFILE["work_authorization"]
        assert page.input_value("#preferred_name") == PROFILE["preferred_name"]
        assert page.input_value("#cover") == PROFILE["cover_letter_snippet"]
        assert page.input_value("#relocate") == PROFILE["willing_to_relocate"]
        assert "Submit" in (page.locator("button").first.inner_text() or "")
        browser.close()

    for key in (
        "email",
        "phone",
        "website",
        "notice_period",
        "current_ctc",
        "expected_ctc",
        "how_heard",
        "work_authorization",
        "cover_letter_snippet",
        "willing_to_relocate",
    ):
        assert key in report["filled"], f"{key} missing from {report['filled']}"


def test_fill_application_form_accepts_file_url_and_never_submits():
    from apply.ats_fill import fill_application_form, playwright_ready

    ok, msg = playwright_ready()
    if not ok:
        pytest.skip(msg)

    # Point runtime profile at the fixture values without touching the live file.
    import config as cfg

    cfg.CANDIDATE.update(
        {
            "name": "Alex Candidate",
            "email": PROFILE["email"],
            "phone": PROFILE["phone"],
            "linkedin": PROFILE["linkedin"],
            "github": PROFILE["github"],
            "location": PROFILE["location"],
            "years_exp": 5,
        }
    )
    cfg.APPLICATION.update(
        {
            "website": PROFILE["website"],
            "notice_period": PROFILE["notice_period"],
            "current_ctc": PROFILE["current_ctc"],
            "expected_ctc": PROFILE["expected_ctc"],
            "how_heard": PROFILE["how_heard"],
            "work_authorization": PROFILE["work_authorization"],
            "preferred_name": PROFILE["preferred_name"],
            "cover_letter_snippet": PROFILE["cover_letter_snippet"],
            "willing_to_relocate": PROFILE["willing_to_relocate"],
        }
    )

    # Avoid reload_discovery_config wiping the monkeypatched values from disk.
    import apply.ats_fill as fill_mod

    original = fill_mod._profile_fields

    def _frozen():
        return dict(PROFILE)

    fill_mod._profile_fields = _frozen  # type: ignore[assignment]
    try:
        report = fill_application_form(FIXTURE.resolve().as_uri(), headless=True)
    finally:
        fill_mod._profile_fields = original  # type: ignore[assignment]

    assert not report.get("errors"), report.get("errors")
    assert report["submit_blocked"] is True
    assert report["submit_detected"] is True
    assert report["ready_for_user_review"] is True
    assert "email" in report["filled"]
    assert "cover_letter_snippet" in report["filled"]
