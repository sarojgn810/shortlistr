"""Today's "Continue Setup" banner must respect real setup, not only the wizard flag."""

from __future__ import annotations

import os
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))

REAL_CV = """# Jordan Lee

**Bengaluru** | **jordan@example.com**

## PROFESSIONAL SUMMARY

SRE with Kubernetes and Terraform experience.

## CORE COMPETENCIES

Kubernetes, Terraform, Prometheus

## PROFESSIONAL EXPERIENCE

### SRE | Acme | 2020 – Present

- Cut MTTR 40% with better alerting.

## EDUCATION

B.S. CS | State U | 2015 – 2019
"""

PLACEHOLDER_CV = """# Your Name

email@example.com | linkedin.com/in/you

## PROFESSIONAL SUMMARY

Your role, years of experience. One measurable win.

## EXPERIENCE

### Your Title | Company | Years

- Bullet with a metric

## EDUCATION

Degree | School | Years
"""


@pytest.fixture
def isolated_onboarding(monkeypatch):
    """Point profile/CV/DB at a temp tree so we never touch the user layer.

    Module-level path snapshots are computed at import — patch the attributes
    on every consumer, not just the env / config module.
    """
    tmp = tempfile.mkdtemp()
    cfg = os.path.join(tmp, "config")
    os.makedirs(cfg)
    cv_path = os.path.join(tmp, "cv.md")
    profile_path = os.path.join(cfg, "profile.yml")
    db_path = os.path.join(tmp, "shortlistr.db")

    import config
    import paths
    import profile_store
    import store.db as db_mod

    monkeypatch.setattr(config, "SHORTLISTR_ROOT", tmp)
    monkeypatch.setattr(config, "DATA_DIR", tmp)
    monkeypatch.setattr(config, "CV_MD_PATH", cv_path)
    monkeypatch.setattr(paths, "CV_PATH", cv_path)
    monkeypatch.setattr(paths, "PROFILE_PATH", profile_path)
    monkeypatch.setattr(profile_store, "PROFILE_PATH", profile_path)
    monkeypatch.setattr(db_mod, "DATA_DIR", tmp)
    monkeypatch.setattr(db_mod, "DB_PATH", db_path)
    db_mod.init_db()

    return {
        "tmp": tmp,
        "cv": cv_path,
        "profile": profile_path,
        "db": db_path,
    }


def _write_profile(path: str, *, name="Jordan Lee", email="jordan@example.com", titles=None):
    titles = titles if titles is not None else ["Site Reliability Engineer"]
    titles_yaml = "\n".join(f"    - {t}" for t in titles) if titles else "    []"
    # Empty list: use literal [] on its own line
    if not titles:
        titles_block = "  target_titles: []"
    else:
        titles_block = "  target_titles:\n" + titles_yaml
    open(path, "w", encoding="utf-8").write(
        f"""candidate:
  name: {name}
  email: {email}
filters:
{titles_block}
llm:
  provider: none
"""
    )


def test_essentials_incomplete_with_placeholder_cv(isolated_onboarding):
    from store.settings import effective_onboarding_complete, onboarding_essentials_gaps

    paths = isolated_onboarding
    _write_profile(paths["profile"])
    open(paths["cv"], "w", encoding="utf-8").write(PLACEHOLDER_CV)

    gaps = onboarding_essentials_gaps()
    assert any("résumé" in g or "resume" in g.lower() or "cv.md" in g for g in gaps)
    done, _ = effective_onboarding_complete({"onboarding_complete": False})
    assert done is False


def test_essentials_incomplete_without_target_titles(isolated_onboarding):
    from store.settings import effective_onboarding_complete, onboarding_essentials_gaps

    paths = isolated_onboarding
    _write_profile(paths["profile"], titles=[])
    open(paths["cv"], "w", encoding="utf-8").write(REAL_CV)

    gaps = onboarding_essentials_gaps()
    assert any("target title" in g for g in gaps)
    done, _ = effective_onboarding_complete({"onboarding_complete": False})
    assert done is False


def test_essentials_met_infers_complete_without_wizard_flag(isolated_onboarding):
    """Users who finish via /profile + /cv must not keep seeing Continue Setup."""
    from store.settings import effective_onboarding_complete, onboarding_essentials_gaps

    paths = isolated_onboarding
    _write_profile(paths["profile"])
    open(paths["cv"], "w", encoding="utf-8").write(REAL_CV)

    assert onboarding_essentials_gaps() == []
    done, gaps = effective_onboarding_complete({"onboarding_complete": False})
    assert done is True
    assert gaps == []


def test_wizard_flag_short_circuits_even_if_files_missing(isolated_onboarding):
    from store.settings import effective_onboarding_complete

    done, gaps = effective_onboarding_complete({"onboarding_complete": True})
    assert done is True
    assert gaps == []


def test_setup_status_reports_inferred_complete(isolated_onboarding, monkeypatch):
    from api.main import create_app
    from fastapi.testclient import TestClient
    from store.settings import set_automation_settings

    paths = isolated_onboarding
    _write_profile(paths["profile"])
    open(paths["cv"], "w", encoding="utf-8").write(REAL_CV)
    # Explicitly leave the sticky flag false — inference must still win.
    set_automation_settings({"onboarding_complete": False})

    # LLM status should not block onboarding_complete.
    monkeypatch.setenv("SHORTLISTR_LLM_API_KEY", "")

    client = TestClient(create_app())
    r = client.get("/setup/status")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["onboarding_complete"] is True
    assert data["onboarding_gaps"] == []
    assert data["automation"]["onboarding_complete"] is False
