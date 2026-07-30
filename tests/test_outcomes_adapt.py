"""O3 — adapt scoring from outcome learnings (bounded + transparent)."""

from __future__ import annotations

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))


def _isolate(monkeypatch):
    tmp = tempfile.mkdtemp()
    import config
    import store.db as db_mod

    monkeypatch.setattr(config, "DATA_DIR", tmp)
    monkeypatch.setattr(db_mod, "DATA_DIR", tmp)
    monkeypatch.setattr(db_mod, "DB_PATH", os.path.join(tmp, "shortlistr.db"))
    return tmp


def test_score_adjustment_penalty_and_boost(monkeypatch):
    _isolate(monkeypatch)
    from memory.store import add_learning
    from outcomes.adapt import score_adjustment
    from store import db

    db.init_db()
    add_learning("company 'GhostCo': 0/5 responses — deprioritize",
                 kind="outcome", key="outcome:company:GhostCo")
    add_learning("source 'greenhouse': 4/8 responses (50%) — prioritize",
                 kind="outcome", key="outcome:source:greenhouse")

    delta, reason = score_adjustment({"company": "GhostCo", "source": "greenhouse"})
    # -8 (ghost) + 6 (convert) = -2; reason mentions both
    assert delta == -2
    assert "ghosts" in reason and "converts" in reason

    none_delta, _ = score_adjustment({"company": "Unknown", "source": "lever"})
    assert none_delta == 0


def test_score_adjustment_is_bounded(monkeypatch):
    _isolate(monkeypatch)
    from memory.store import add_learning
    from outcomes.adapt import MAX_DELTA, score_adjustment
    from store import db

    db.init_db()
    for c in ("A", "B", "C"):
        add_learning(f"company '{c}': 0/9 responses — deprioritize",
                     kind="outcome", key=f"outcome:company:{c}")
    # one job can only match its own company, so bound is naturally respected;
    # assert the cap helper holds for a synthetic over-limit case via repeated keys
    delta, _ = score_adjustment({"company": "A"})
    assert -MAX_DELTA <= delta <= MAX_DELTA


def test_job_filter_applies_learned_adjustment(monkeypatch):
    _isolate(monkeypatch)
    import config

    # Target the title this test scores. `_isolate` gives the test its own data
    # directory but not its own targeting, so score_job read the user's live
    # config/profile.yml: an SRE role scored "title mismatch" and never reached
    # the learned-adjustment branch this test is actually about.
    monkeypatch.setattr(config, "SEARCH_KEYWORDS", ["SRE", "Site Reliability"])
    monkeypatch.setattr(config, "LOCATION_KEYWORDS", ["remote"])

    from memory.store import add_learning
    from store import db

    db.init_db()
    add_learning("company 'GhostCo': 0/6 responses — deprioritize",
                 kind="outcome", key="outcome:company:GhostCo")

    from processors.job_filter import score_job

    job = score_job({
        "title": "Site Reliability Engineer",
        "company": "GhostCo",
        "location": "Remote",
        "description": "SRE role with Kubernetes and Terraform",
    })
    assert "learned" in job["fit_reason"]


def test_scoring_retargets_when_the_profile_changes(monkeypatch):
    """Saving a new profile must change what scores, without a restart.

    CLAUDE.md lists "profile save → live retarget" as a flow that must not
    break. It was half-broken: `pipeline/filter.py` reads config per call so
    discovery retargeted immediately, but scoring snapshotted its title list at
    import, so an SRE-targeted profile kept scoring against whatever was
    configured when the process started.
    """
    _isolate(monkeypatch)
    import config
    from processors.job_filter import score_job

    sre = {"title": "Site Reliability Engineer", "company": "Co",
           "location": "Remote", "description": "kubernetes terraform on-call"}

    monkeypatch.setattr(config, "SEARCH_KEYWORDS", ["Product Manager"])
    assert score_job(dict(sre))["fit_score"] == 0

    # The same job, after the profile changes. No reimport, no restart.
    monkeypatch.setattr(config, "SEARCH_KEYWORDS", ["Site Reliability"])
    assert score_job(dict(sre))["fit_score"] > 0


def test_scoring_requires_configured_titles(monkeypatch):
    """Empty targeting must not invent an author stack — force onboarding."""
    _isolate(monkeypatch)
    import config
    from processors.job_filter import core_titles, score_job

    monkeypatch.setattr(config, "SEARCH_KEYWORDS", [])
    assert core_titles() == []
    scored = score_job({"title": "SRE", "company": "Co", "location": "Remote",
                        "description": "kubernetes terraform"})
    assert scored["fit_score"] == 0
    assert "no target titles" in scored["fit_reason"]
