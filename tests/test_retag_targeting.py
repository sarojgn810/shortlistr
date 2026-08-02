"""Changing targeting must re-judge jobs already in the DB.

Mismatches are soft-tagged off_target — never hard-deleted. User discard /
skip remains the only Discover delete path.
"""

from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "automation"))

import config  # noqa: E402


def _write_profile(root: str, *, titles: list[str], locations: list[str]) -> None:
    os.makedirs(os.path.join(root, "config"), exist_ok=True)
    tl = "".join(f"\n      - {t}" for t in titles) or " []"
    lc = "".join(f"\n      - {loc}" for loc in locations) or " []"
    with open(os.path.join(root, "config", "profile.yml"), "w", encoding="utf-8") as f:
        f.write(f"filters:\n  target_titles:{tl}\n  preferred_locations:{lc}\n")


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    import store.db as db_mod

    monkeypatch.setattr(db_mod, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(db_mod, "DB_PATH", str(tmp_path / "shortlistr.db"))
    monkeypatch.setattr(config, "SHORTLISTR_ROOT", str(tmp_path))
    yield tmp_path
    monkeypatch.undo()
    config.reload_discovery_config()


def _seed_job(*, relevance: str = "off_target") -> str:
    from models.job import JobRecord
    from store import db as store

    job = JobRecord(
        url="https://boards.greenhouse.io/acme/jobs/retag-1",
        source="Greenhouse",
        company="Acme",
        title="Site Reliability Engineer",
        location="Hyderabad, India",
        jd_text="We run Kubernetes, Terraform and Prometheus at scale. " * 10,
        fit_score=0 if relevance == "off_target" else 80,
        metadata={"discovery_relevance": relevance},
    )
    store.upsert_jobs([job])
    return job.job_id


def _stored(job_id: str) -> dict | None:
    from store import db as store

    with store.db() as conn:
        row = conn.execute(
            "SELECT fit_score, metadata_json FROM jobs WHERE id = ?", (job_id,)
        ).fetchone()
    if row is None:
        return None
    meta = json.loads(dict(row)["metadata_json"] or "{}")
    return {
        "fit_score": dict(row)["fit_score"],
        "relevance": meta.get("discovery_relevance"),
    }


def test_retag_promotes_jobs_that_now_match(isolated):
    from orchestrator.discovery import retag_existing_jobs

    _write_profile(str(isolated), titles=["Product Manager"], locations=["Berlin"])
    config.reload_discovery_config()
    job_id = _seed_job(relevance="off_target")
    assert _stored(job_id)["relevance"] == "off_target"

    _write_profile(str(isolated), titles=["Site Reliability Engineer"], locations=["Hyderabad"])
    config.reload_discovery_config()
    result = retag_existing_jobs()

    assert result["relevant"] == 1
    assert result["purged"] == 0
    stored = _stored(job_id)
    assert stored is not None
    assert stored["relevance"] == "relevant"
    assert stored["fit_score"] >= 40


def test_retag_marks_off_target_instead_of_deleting(isolated):
    from orchestrator.discovery import retag_existing_jobs

    _write_profile(str(isolated), titles=["Site Reliability Engineer"], locations=["Hyderabad"])
    config.reload_discovery_config()
    job_id = _seed_job(relevance="relevant")
    retag_existing_jobs()
    assert _stored(job_id)["relevance"] == "relevant"

    _write_profile(str(isolated), titles=["Product Manager"], locations=["Berlin"])
    config.reload_discovery_config()
    result = retag_existing_jobs()

    assert result["purged"] == 0
    assert result["off_target"] == 1
    stored = _stored(job_id)
    assert stored is not None
    assert stored["relevance"] == "off_target"


def test_retag_keeps_applied_jobs_even_when_off_target(isolated):
    from orchestrator.discovery import retag_existing_jobs
    from store import db as store

    _write_profile(str(isolated), titles=["Site Reliability Engineer"], locations=["Hyderabad"])
    config.reload_discovery_config()
    job_id = _seed_job(relevance="relevant")
    with store.db() as conn:
        conn.execute(
            "INSERT INTO applications (job_id, status, applied_date) VALUES (?, 'applied', date('now'))",
            (job_id,),
        )

    _write_profile(str(isolated), titles=["Product Manager"], locations=["Berlin"])
    config.reload_discovery_config()
    result = retag_existing_jobs()

    assert result["purged"] == 0
    assert result["protected"] == 1
    stored = _stored(job_id)
    assert stored is not None
    assert stored["relevance"] == "off_target"


def test_profile_save_retags_when_targeting_changes(isolated, monkeypatch):
    import profile_store

    profile_path = os.path.join(str(isolated), "config", "profile.yml")
    monkeypatch.setattr(profile_store, "PROFILE_PATH", profile_path)
    monkeypatch.setattr(profile_store, "ENV_FILE", os.path.join(str(isolated), ".env"))

    _write_profile(str(isolated), titles=["Product Manager"], locations=["Berlin"])
    config.reload_discovery_config()
    job_id = _seed_job(relevance="off_target")

    profile_store.save_profile_from_ui(
        {
            "name": "Alex Candidate",
            "email": "alex@example.com",
            "target_titles": ["Site Reliability Engineer"],
            "preferred_locations": ["Hyderabad"],
        }
    )

    stored = _stored(job_id)
    assert stored is not None
    assert stored["relevance"] == "relevant"
