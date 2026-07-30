"""CV onboarding and scheduler tests."""

from __future__ import annotations

import os
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))

SAMPLE_CV = """# Jane Doe

**SF** | **jane@example.com**

## PROFESSIONAL SUMMARY

SRE with 5 years and 40% MTTR reduction on Kubernetes platforms.

## CORE COMPETENCIES

Kubernetes, Terraform, Prometheus, Python

## PROFESSIONAL EXPERIENCE

### SRE | Acme | 2020 – Present

- Cut incidents 30% with SLO-driven alerting.

## EDUCATION

B.S. CS | State U | 2015 – 2019

## CERTIFICATIONS

- AWS CCP
"""


def test_parse_cv_sections():
    from cv.parser import parse_cv_markdown

    s = parse_cv_markdown(SAMPLE_CV)
    assert s.name == "Jane Doe"
    assert "Kubernetes" in s.skills
    assert "MTTR" in s.summary
    assert "SRE" in s.experience


def test_ats_score_strong():
    from cv.ats_score import score_ats_readiness

    r = score_ats_readiness(SAMPLE_CV, template_id="classic-ats")
    assert r["score"] >= 90
    assert r["content_score"] >= 85
    assert r["tier"] in ("strong", "excellent")
    name = next(c for c in r["checks"] if c["label"] == "Name")
    assert name["ok"] is True


def test_ats_content_only_no_template_penalty():
    from cv.ats_score import score_ats_readiness

    r = score_ats_readiness(SAMPLE_CV, include_template=False)
    assert r["score"] >= 85
    assert not any(c["label"] == "ATS template selected" for c in r["checks"])
    name_check = next(c for c in r["checks"] if c["label"] == "Name")
    assert name_check["ok"] is True


def test_build_latex_contains_name():
    from cv.latex_builder import build_latex

    tex = build_latex(SAMPLE_CV, "classic-ats")
    assert "Jane Doe" in tex
    assert "documentclass" in tex


@pytest.fixture
def isolated_settings(monkeypatch):
    tmp = tempfile.mkdtemp()
    import config
    import store.db as db_mod

    monkeypatch.setattr(config, "DATA_DIR", tmp)
    monkeypatch.setattr(db_mod, "DATA_DIR", tmp)
    monkeypatch.setattr(db_mod, "DB_PATH", os.path.join(tmp, "shortlistr.db"))
    return tmp


def test_automation_settings_roundtrip(isolated_settings):
    from store.settings import get_automation_settings, set_automation_settings

    set_automation_settings({"scan_enabled": True, "scan_interval_hours": 48})
    s = get_automation_settings()
    assert s["scan_enabled"] is True
    assert s["scan_interval_hours"] == 48


def test_scan_is_due_when_never_run(isolated_settings, monkeypatch):
    """A never-scanned instance is due, once the boot grace has passed.

    `_BOOT_TIME` used to be patched to 0, which quietly assumed
    `time.monotonic()` returns something large. On Linux it returns uptime, so
    on a CI runner that booted seconds ago the 120s grace had *not* elapsed and
    this failed — while passing on any laptop that had been on for a while.
    Anchor it to now instead, so the test states the condition it means: boot
    was long enough ago.
    """
    import time

    import scheduler.scan_scheduler as sched
    from scheduler.scan_scheduler import scan_is_due
    from store.settings import set_automation_settings

    monkeypatch.setattr(sched, "_BOOT_TIME",
                        time.monotonic() - sched._BOOT_GRACE_SECONDS - 1)
    # Essentials must be met (or the sticky flag set) — a fresh clone waits for
    # onboarding before any background scan.
    set_automation_settings({
        "scan_enabled": True,
        "last_scan_at": None,
        "onboarding_complete": True,
    })
    assert scan_is_due() is True


def test_scan_is_not_due_before_onboarding(isolated_settings, monkeypatch):
    """Background discovery must not run against the empty-profile fallback
    while the wizard is still open."""
    import time

    import scheduler.scan_scheduler as sched
    from scheduler.scan_scheduler import scan_is_due
    from store.settings import set_automation_settings

    monkeypatch.setattr(sched, "_BOOT_TIME",
                        time.monotonic() - sched._BOOT_GRACE_SECONDS - 1)
    # Essentials read live paths unless patched — point them at nothing so this
    # fixture cannot inherit the developer's completed setup.
    monkeypatch.setattr(
        "store.settings.effective_onboarding_complete",
        lambda settings=None: (False, ["profile"]),
    )
    set_automation_settings({
        "scan_enabled": True,
        "last_scan_at": None,
        "onboarding_complete": False,
    })
    assert scan_is_due() is False


def test_scan_is_not_due_during_the_boot_grace(isolated_settings, monkeypatch):
    """The other half, which nothing covered. The grace exists so a fresh clone
    does not scan against a seeded profile before onboarding — and it is the
    reason `make ingest` calls the orchestrator directly rather than going
    through here."""
    import time

    import scheduler.scan_scheduler as sched
    from scheduler.scan_scheduler import scan_is_due
    from store.settings import set_automation_settings

    monkeypatch.setattr(sched, "_BOOT_TIME", time.monotonic())
    set_automation_settings({
        "scan_enabled": True,
        "last_scan_at": None,
        "onboarding_complete": True,
    })
    assert scan_is_due() is False


def test_cv_save_api():
    from api.main import create_app
    from fastapi.testclient import TestClient

    app = create_app()
    client = TestClient(app)
    resp = client.post("/cv/save", json={"markdown": SAMPLE_CV})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "path" in data
    assert data["ats"]["score"] >= 0
    assert data["ats"]["job_match_percent"] == data["ats"]["score"]
    assert os.path.isfile(data["path"])


def test_cv_preview_api():
    from api.main import create_app
    from fastapi.testclient import TestClient

    app = create_app()
    client = TestClient(app)
    resp = client.post("/cv/preview", json={"template_id": "classic-ats", "markdown": SAMPLE_CV})
    assert resp.status_code == 200, resp.text
    html = resp.json()["html"]
    assert "Jane Doe" in html  # name comes from the posted SAMPLE_CV markdown
    assert "<!DOCTYPE html>" in html
    assert "a4-sheet" in html

    tpl = client.get("/cv/templates/modern-minimal/preview?use_sample=true")
    assert tpl.status_code == 200
    assert "Alex Candidate" in tpl.json()["html"]


def test_cv_delete_api():
    from api.main import create_app
    from fastapi.testclient import TestClient

    app = create_app()
    client = TestClient(app)
    client.post("/cv/save", json={"markdown": SAMPLE_CV})
    del_resp = client.delete("/cv")
    assert del_resp.status_code == 200
    assert client.get("/cv/content").json()["markdown"] == ""
