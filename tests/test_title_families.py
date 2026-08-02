"""Title-family targeting: a profile role must be searched and matched in every
spelling boards use, and a capped search budget must cover every role family.

Regression: a profile listing four SRE variants plus MLOps and AIOps only ever
searched "Site Reliability Engineer" (sources took SEARCH_KEYWORDS[:5] and Apify
ran one pair), and "Senior ML Ops Engineer" was filtered out as off-target
because the keyword was literally "MLOps Engineer".
"""

from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))

import config as cfg  # noqa: E402
from models.job import JobRecord  # noqa: E402
from pipeline.filter import passes_title_location  # noqa: E402


@pytest.fixture
def sre_mlops_aiops_profile(monkeypatch):
    monkeypatch.setattr(
        cfg,
        "SEARCH_KEYWORDS",
        cfg._expand_titles([
            "Site Reliability Engineer",
            "SRE",
            "Principal Site Reliability Engineer",
            "Senior Site Reliability Engineer",
            "MLOps Engineer",
            "AIOps Engineer",
        ]),
    )
    monkeypatch.setattr(
        cfg, "LOCATION_KEYWORDS", cfg._expand_location_keywords(["Bangalore", "Remote"])
    )
    return cfg.SEARCH_KEYWORDS


def _job(title: str, location: str = "Bengaluru") -> JobRecord:
    return JobRecord(
        url="https://example.com/j",
        source="Greenhouse",
        company="Example",
        title=title,
        location=location,
        job_id="j1",
    )


@pytest.mark.parametrize(
    "title",
    [
        "Senior ML Ops Engineer, AI Platform Team",
        "MLOps Lead",
        "Machine Learning Operations Engineer",
        "AIOps Specialist",
        "AI Ops Engineer",
        "Staff Site Reliability Engineer",
    ],
)
def test_board_spellings_of_a_targeted_role_pass(sre_mlops_aiops_profile, title):
    assert passes_title_location(_job(title))


@pytest.mark.parametrize(
    "title",
    [
        "Machine Learning Scientist",
        "Research Engineer, Machine Learning",
        "Sales Development Representative",
    ],
)
def test_adjacent_roles_still_dropped(sre_mlops_aiops_profile, title):
    """Aliases stay tight — MLOps must not drag in ML research roles."""
    assert not passes_title_location(_job(title))


def test_search_titles_covers_every_family_before_seniority_variants(
    sre_mlops_aiops_profile,
):
    picked = [t.lower() for t in cfg.search_titles(3)]
    assert {cfg.title_family(t) for t in picked} == {"sre", "mlops", "aiops"}


def test_search_locations_collapses_city_spellings(sre_mlops_aiops_profile):
    """Bangalore/Bengaluru/blr are one city — one paid search, not three."""
    assert cfg.search_locations(3) == ["bangalore"]


def test_title_family_ignores_seniority():
    assert (
        cfg.title_family("Principal Site Reliability Engineer")
        == cfg.title_family("SRE II")
        == "sre"
    )


def test_apify_rotates_families_across_boards(monkeypatch, sre_mlops_aiops_profile):
    """max_pairs=1 must not mean "run the same one query on all boards"."""
    from sources.adapters import apify_adapter as mod

    queried: list[tuple[str, str]] = []

    def fake_run_actor(actor, run_input, **kwargs):
        queried.append((actor, str(run_input)))
        return []

    monkeypatch.setattr(mod, "run_actor", fake_run_actor)
    monkeypatch.setattr(mod, "get_apify_token", lambda: "tok")
    monkeypatch.setattr(
        mod,
        "_apify_config",
        lambda: {
            "boards": ["naukri", "linkedin", "indeed"],
            "max_pairs": 1,
            "limit": 5,
            "timeout_secs": 5,
        },
    )

    mod.ApifyAdapter().fetch_raw()

    blob = " ".join(payload.lower() for _, payload in queried)
    assert "mlops" in blob or "ml ops" in blob
    assert "aiops" in blob or "ai ops" in blob
    assert "site reliability" in blob
