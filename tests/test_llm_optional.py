"""No-LLM heuristic eval + cover letter + chat fallback."""

from __future__ import annotations

import os
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    import config
    import store.db as db_mod

    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "SHORTLISTR_ROOT", str(tmp_path))
    monkeypatch.setattr(db_mod, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(db_mod, "DB_PATH", str(tmp_path / "shortlistr.db"))
    cv = tmp_path / "cv.md"
    cv.write_text(
        """# Ada Lovelace

## PROFESSIONAL SUMMARY
Product manager with analytics background.

## CORE COMPETENCIES
Product strategy, SQL, A/B testing, Roadmaps, Stakeholder management

## PROFESSIONAL EXPERIENCE

### Product Manager | Contoso | 2019 – Present

- Grew activation 25% by shipping onboarding experiments with SQL-backed analysis.
- Owned roadmap for analytics platform used by 40 internal teams.
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "CV_MD_PATH", str(cv))
    db_mod.init_db()
    return tmp_path


def test_heuristic_eval_fills_all_ag_blocks(isolated, monkeypatch):
    import config

    monkeypatch.setitem(config.LLM_CONFIG, "provider", "none")
    from eval.service import evaluate_job_text

    result = evaluate_job_text(
        """Product Manager — Analytics Platform

Requirements:
- Own product roadmap
- SQL and A/B testing
- Stakeholder management

https://boards.greenhouse.io/contoso/jobs/99
""",
        url="https://boards.greenhouse.io/contoso/jobs/99",
        company="Contoso",
        role="Product Manager",
    )
    d = result.to_dict()
    assert d["eval_mode"] == "template"
    assert d["template_only"] is True
    for key in "ABCDEFG":
        assert d["blocks"].get(key), f"missing block {key}"
    assert d["legitimacy"] == "likely"  # greenhouse host
    assert result.score >= 2.5


def test_cover_template_uses_cv_not_sre_map(isolated, monkeypatch):
    import config

    monkeypatch.setitem(config.LLM_CONFIG, "provider", "none")
    monkeypatch.setattr(config, "CANDIDATE", {
        "name": "Ada Lovelace",
        "email": "ada@example.com",
        "years_exp": 6,
    }, raising=False)
    # Reload application of CANDIDATE inside cover_letter module
    import processors.cover_letter as cl

    monkeypatch.setattr(cl, "CANDIDATE", {
        "name": "Ada Lovelace",
        "email": "ada@example.com",
        "phone": "",
        "linkedin": "",
        "github": "",
        "years_exp": 6,
    })

    out = cl.generate_cover_letter({
        "company": "Contoso",
        "title": "Product Manager",
        "jd_snippet": "Looking for SQL, A/B testing, and roadmap ownership.",
    })
    assert out["mode"] == "template"
    body = out["body"].lower()
    assert "kubernetes" not in body
    assert "sre" not in body or "product" in body
    assert "activation" in body or "sql" in body or "roadmap" in body


def test_chat_fallback_mentions_connections(isolated, monkeypatch):
    from agent import chat as chat_mod

    monkeypatch.setattr("llm.get_llm", lambda: None)
    res = chat_mod.chat("hello there", tenant_id="default")
    assert "Connections" in res["reply"]
    assert "status" in res["reply"].lower()


def test_llm_status_tool_calling_tracks_availability(monkeypatch):
    import config
    from llm import status as status_mod

    monkeypatch.setitem(config.LLM_CONFIG, "provider", "none")
    monkeypatch.setitem(config.LLM_CONFIG, "api_key", "")
    st = status_mod.llm_status()
    assert st["features"]["tool_calling"] is False
    assert "Connections" in st["hint"] or st["reason"] == "not_configured"
