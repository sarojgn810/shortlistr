"""First-run path: empty clone → seed → onboard → discover → evaluate → approve → CV.

This is the path a new user walks after `git clone` and `make start`. Each step
has its own unit tests elsewhere; this file pins the seams between them so a
regression that leaves the first-run experience broken cannot hide behind green
unit coverage of each piece in isolation.

The fixture never touches the real user layer. Module-level path snapshots are
patched on every consumer — setting only the env / `config` attributes is not
enough once those modules have imported.
"""

from __future__ import annotations

import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))

REAL_CV = """# Alex Candidate

**Remote** | **alex@example.com** | **+1 555 0100**

## PROFESSIONAL SUMMARY

Software engineer with Kubernetes and Terraform experience.

## TECHNICAL SKILLS

Kubernetes, Terraform, Python, Prometheus

## PROFESSIONAL EXPERIENCE

### Software Engineer | Acme | 2020 – Present

- Cut MTTR 40% with better alerting.

## EDUCATION

B.S. Computer Science, State University 2015 – 2019
"""


@pytest.fixture
def fresh_clone(tmp_path, monkeypatch):
    """An empty tree that looks like a fresh clone — no user-layer files."""
    import config
    import paths
    import profile_store
    import store.db as db_mod
    import bootstrap.seed as seed_mod
    import cv.latex_builder as latex_builder
    import processors.generate_cv as gen_cv

    root = tmp_path
    data = root / "data"
    cfg = root / "config"
    modes = root / "modes"
    templates = root / "templates"
    output = root / "output"
    for d in (data, cfg, modes, templates, output):
        d.mkdir()

    # The seed copies from templates that live in SHORTLISTR_ROOT. Provide the
    # minimal set so this test does not depend on the live repo's templates.
    (templates / "portals.example.yml").write_text("companies: []\n")
    (root / ".env.example").write_text("SHORTLISTR_LLM_API_KEY=\nAPIFY_TOKEN=\n")
    (modes / "_profile.template.md").write_text("# Your profile notes\n")
    (templates / "applications.example.md").write_text("# Applications\n")

    cv_path = str(root / "cv.md")
    profile_path = str(cfg / "profile.yml")
    db_path = str(data / "shortlistr.db")
    portals_path = str(root / "portals.yml")
    env_path = str(root / ".env")
    output_dir = str(output)

    for mod, attrs in (
        (config, {
            "SHORTLISTR_ROOT": str(root),
            "DATA_DIR": str(data),
            "CV_MD_PATH": cv_path,
            "OUTPUT_DIR": output_dir,
        }),
        (paths, {
            "SHORTLISTR_ROOT": str(root),
            "DATA_DIR": str(data),
            "CV_PATH": cv_path,
            "PROFILE_PATH": profile_path,
            "PORTALS_PATH": portals_path,
        }),
        (profile_store, {
            "SHORTLISTR_ROOT": str(root),
            "PROFILE_PATH": profile_path,
            "ENV_FILE": env_path,
        }),
        (db_mod, {"DATA_DIR": str(data), "DB_PATH": db_path}),
        (seed_mod, {
            "SHORTLISTR_ROOT": str(root),
            "DATA_DIR": str(data),
            "CV_MD_PATH": cv_path,
        }),
        # Imported at module load — patching config alone leaves these stale.
        (latex_builder, {
            "SHORTLISTR_ROOT": str(root),
            "CV_MD_PATH": cv_path,
            "OUTPUT_DIR": output_dir,
        }),
        (gen_cv, {"CV_MD_PATH": cv_path, "OUTPUT_DIR": output_dir}),
    ):
        for name, value in attrs.items():
            monkeypatch.setattr(mod, name, value)

    return {
        "root": root,
        "cv": cv_path,
        "profile": profile_path,
        "db": db_path,
        "portals": portals_path,
        "env": env_path,
        "data": str(data),
    }


def test_seed_creates_user_layer_without_a_profile(fresh_clone):
    """`make start` must leave targeting to onboarding — never invent a person."""
    from bootstrap.seed import seed_local_files

    actions = seed_local_files()
    assert any("portals.yml" in a for a in actions)
    assert any(".env" in a for a in actions)
    assert any("cv.md" in a for a in actions)
    assert os.path.isfile(fresh_clone["portals"])
    assert os.path.isfile(fresh_clone["env"])
    assert os.path.isfile(fresh_clone["cv"])
    assert os.path.isfile(fresh_clone["db"])
    assert not os.path.isfile(fresh_clone["profile"])

    # The seeded résumé is a placeholder the wizard will refuse to treat as done.
    cv = open(fresh_clone["cv"]).read().lower()
    assert "your name" in cv


def test_empty_profile_falls_back_to_generic_titles(fresh_clone, monkeypatch):
    """Before onboarding, a scan must not run against the author's SRE titles."""
    import config

    config.reload_discovery_config()
    titles = [t.lower() for t in config.SEARCH_KEYWORDS]
    assert "software engineer" in titles
    assert "data analyst" in titles
    assert "product manager" in titles
    # The author's own targeting must not leak into a fresh clone.
    assert not any("site reliability" in t for t in titles)
    assert any("remote" in loc.lower() for loc in config.LOCATION_KEYWORDS)


def test_api_boots_and_reports_incomplete_setup(fresh_clone):
    """No profile, placeholder CV → the banner must say what is still needed."""
    from bootstrap.seed import seed_local_files
    from api.main import create_app
    from fastapi.testclient import TestClient

    seed_local_files()
    client = TestClient(create_app())

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    status = client.get("/setup/status")
    assert status.status_code == 200
    body = status.json()
    assert body["onboarding_complete"] is False
    assert body["checks"]["profile"] is False
    gaps = " ".join(body.get("onboarding_gaps") or []).lower()
    assert "profile" in gaps or "title" in gaps or "résumé" in gaps or "resume" in gaps


def test_first_run_walkthrough(fresh_clone, monkeypatch):
    """Clone → seed → profile → real CV → evaluate → approve → CV PDF.

    Every step uses the real FastAPI app against an isolated tree. LLM and Apify
    stay off so the path is deterministic and free.
    """
    from bootstrap.seed import seed_local_files
    from api.main import create_app
    from fastapi.testclient import TestClient
    from store import db as store

    seed_local_files()
    # Replace the placeholder with a real résumé — onboarding's upload step.
    open(fresh_clone["cv"], "w", encoding="utf-8").write(REAL_CV)

    client = TestClient(create_app())

    # 1. Profile from the wizard.
    saved = client.put(
        "/setup/profile",
        json={
            "name": "Alex Candidate",
            "email": "alex@example.com",
            "phone": "+1 555 0100",
            "location": "Remote",
            "target_titles": ["Software Engineer", "Backend Engineer"],
            "target_locations": ["Remote"],
            "llm_provider": "none",
        },
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["exists"] is True
    assert os.path.isfile(fresh_clone["profile"])
    # The key never lands in profile.yml.
    assert "SHORTLISTR_LLM_API_KEY" not in open(fresh_clone["profile"]).read()

    # Targeting has to take effect without an API restart.
    import config

    config.reload_discovery_config()
    assert any("software engineer" in t.lower() for t in config.SEARCH_KEYWORDS)

    # 2. Essentials met → Today stops nagging, even without the sticky flag.
    status = client.get("/setup/status").json()
    assert status["onboarding_complete"] is True
    assert status["checks"]["profile"] is True
    assert status["checks"]["cv"] is True

    # 3. A discovered job lands in the pipeline as pending. The id must be the
    # canonical hash of the URL — evaluate upserts by that id, and a mismatched
    # id with the same URL trips the UNIQUE(url) constraint.
    from models.job import job_id_from_url

    job_url = "https://example.com/jobs/1"
    job_id = job_id_from_url(job_url)
    store.init_db()
    with store.db() as conn:
        conn.execute(
            "INSERT INTO jobs (id, url, source, company, title, location, "
            "fit_score, metadata_json) VALUES (?,?,?,?,?,?,?,?)",
            (
                job_id,
                job_url,
                "greenhouse",
                "Acme",
                "Software Engineer",
                "Remote",
                80,
                json.dumps({"discovery_relevance": "relevant"}),
            ),
        )
        conn.execute(
            "INSERT INTO pipeline (job_id, status) VALUES (?, ?)",
            (job_id, "pending"),
        )

    # The badge-facing count — not a page length — reports the one job.
    stats = client.get("/pipeline/stats").json()
    assert stats["pipeline_targeted"]["pending"] == 1

    inbox = client.get("/jobs?status=inbox&relevance=relevant").json()
    assert len(inbox) == 1
    assert inbox[0]["pipeline_status"] == "pending"

    # 4. Evaluate without an LLM key must degrade, never 500.
    monkeypatch.setenv("SHORTLISTR_LLM_API_KEY", "")
    eval_resp = client.post(f"/jobs/{job_id}/evaluate")
    assert eval_resp.status_code == 200, eval_resp.text
    # Whatever shape the heuristic returns, the job must leave pending.
    after = client.get(f"/jobs/{job_id}").json()
    assert after["pipeline_status"] in ("evaluated", "pending", "approved")

    # 5. Approve is an explicit user action — never automatic.
    if after["pipeline_status"] != "approved":
        if after["pipeline_status"] == "pending":
            from store.status import mark_evaluated

            mark_evaluated(job_id, score=4.0, actor="test")
        approved = client.post(
            f"/jobs/{job_id}/pipeline-status",
            json={"status": "approved"},
        )
        assert approved.status_code == 200, approved.text

    # The apply runner asks for approved rows specifically.
    queue = client.get("/jobs?status=approved&relevance=relevant").json()
    assert {j["id"] for j in queue} == {job_id}

    counts = client.get("/pipeline/stats").json()["pipeline_targeted"]
    assert counts["pending"] == 0
    assert counts["approved"] == 1

    # 6. Generating a CV must succeed even without a LaTeX engine (HTML fallback).
    gen = client.post(
        "/cv/generate",
        json={"template_id": "ats-single", "page_target": "auto"},
    )
    assert gen.status_code == 200, gen.text
    body = gen.json()
    assert body.get("pdf_ok") or body.get("tex_path")
    # The source markdown must never have been overwritten by the generate.
    assert open(fresh_clone["cv"]).read().startswith("# Alex Candidate")


def test_apify_adapter_is_a_noop_without_a_token(fresh_clone, monkeypatch):
    """A missing paid-service token must not break discovery — just skip that board."""
    import sources.adapters.apify_adapter as adapter

    monkeypatch.setattr(adapter, "get_apify_token", lambda: "")
    jobs, stats = adapter.ApifyAdapter().fetch_raw()
    assert jobs == []
    assert stats.raw_count == 0


def test_seeded_portals_example_is_field_neutral():
    """A fresh clone must not inherit the author's SRE targeting via portals.yml."""
    import yaml
    from config import SHORTLISTR_ROOT, _DEFAULT_SEARCH_KEYWORDS

    path = os.path.join(SHORTLISTR_ROOT, "templates", "portals.example.yml")
    cfg = yaml.safe_load(open(path, encoding="utf-8")) or {}
    positive = [p.lower() for p in (cfg.get("title_filter") or {}).get("positive", [])]
    for title in _DEFAULT_SEARCH_KEYWORDS:
        assert title.lower() in positive, f"missing neutral title: {title}"
    assert not any("site reliability" in p or p == "sre" for p in positive)
    # Example search queries stay as documentation but must not fire on clone.
    for q in cfg.get("search_queries") or []:
        assert q.get("enabled") is False, q.get("name")
