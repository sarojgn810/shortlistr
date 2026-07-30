"""Preferred locations must narrow the discovery search (e.g. 'Hyderabad only')."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "automation"))

import config  # noqa: E402


def _write_profile(root: str, *, locations: list[str]) -> None:
    os.makedirs(os.path.join(root, "config"), exist_ok=True)
    locs = "".join(f"\n      - {c}" for c in locations) or " []"
    with open(os.path.join(root, "config", "profile.yml"), "w", encoding="utf-8") as f:
        f.write(
            "filters:\n"
            "  target_titles: [Site Reliability Engineer]\n"
            f"  preferred_locations:{locs}\n"
        )


def _reload(tmp_path, **kw) -> list[str]:
    root = str(tmp_path)
    _write_profile(root, **kw)
    original = config.SHORTLISTR_ROOT
    try:
        config.SHORTLISTR_ROOT = root
        config.reload_discovery_config()
        return list(config.LOCATION_KEYWORDS)
    finally:
        config.SHORTLISTR_ROOT = original


def test_single_preferred_location_narrows_to_that_city(tmp_path):
    locs = _reload(tmp_path, locations=["Hyderabad"])
    assert "hyderabad" in locs
    # Airport / short aliases are expanded so board text like "Hyd" still matches.
    assert "hyd" in locs
    assert "bangalore" not in locs
    assert "india" not in locs


def test_blank_preferred_falls_back_to_default(tmp_path):
    # Neutral, global-first default when the user hasn't set locations: remote only,
    # no India lock (targeting is meant to come from the résumé/profile).
    locs = _reload(tmp_path, locations=[])
    assert "remote" in locs
    assert "india" not in locs


def test_preferred_with_remote_keeps_remote_keyword(tmp_path):
    locs = _reload(tmp_path, locations=["Hyderabad", "Remote"])
    assert "hyderabad" in locs
    assert "remote" in locs
    assert "bangalore" not in locs


def test_remote_strict_when_only_remote_locations(tmp_path):
    _write_profile(str(tmp_path), locations=["Remote"])
    original = config.SHORTLISTR_ROOT
    try:
        config.SHORTLISTR_ROOT = str(tmp_path)
        config.reload_discovery_config()
        assert config.REMOTE_STRICT is True
    finally:
        config.SHORTLISTR_ROOT = original


def test_not_remote_strict_when_city_included(tmp_path):
    _write_profile(str(tmp_path), locations=["Bangalore", "Remote"])
    original = config.SHORTLISTR_ROOT
    try:
        config.SHORTLISTR_ROOT = str(tmp_path)
        config.reload_discovery_config()
        assert config.REMOTE_STRICT is False
    finally:
        config.SHORTLISTR_ROOT = original


def test_wants_remote_true_when_remote_in_locations(tmp_path):
    _write_profile(str(tmp_path), locations=["Bangalore", "Remote"])
    original = config.SHORTLISTR_ROOT
    try:
        config.SHORTLISTR_ROOT = str(tmp_path)
        config.reload_discovery_config()
        assert config.WANTS_REMOTE is True
    finally:
        config.SHORTLISTR_ROOT = original


def test_wants_remote_false_when_only_cities(tmp_path):
    _write_profile(str(tmp_path), locations=["Bangalore", "Bengaluru"])
    original = config.SHORTLISTR_ROOT
    try:
        config.SHORTLISTR_ROOT = str(tmp_path)
        config.reload_discovery_config()
        assert config.WANTS_REMOTE is False
    finally:
        config.SHORTLISTR_ROOT = original


def test_remote_aggregator_filtered_when_no_remote_wanted(tmp_path):
    """Remote-only sources (Himalayas etc.) should be filtered out when
    the user only wants Indian cities (no 'Remote' in preferred_locations)."""
    from models.job import JobRecord
    from pipeline.filter import passes_title_location

    _write_profile(str(tmp_path), locations=["Bangalore"])
    original = config.SHORTLISTR_ROOT
    try:
        config.SHORTLISTR_ROOT = str(tmp_path)
        config.reload_discovery_config()

        remote_job = JobRecord(
            url="https://example.com/job/1",
            source="Himalayas",
            company="TestCo",
            title="Site Reliability Engineer",
            location="Remote",
        )
        assert passes_title_location(remote_job) is False
    finally:
        config.SHORTLISTR_ROOT = original


def test_remote_aggregator_passes_when_remote_wanted(tmp_path):
    """Remote-only sources should pass when user has 'Remote' in preferred_locations."""
    from models.job import JobRecord
    from pipeline.filter import passes_title_location

    _write_profile(str(tmp_path), locations=["Bangalore", "Remote"])
    original = config.SHORTLISTR_ROOT
    try:
        config.SHORTLISTR_ROOT = str(tmp_path)
        config.reload_discovery_config()

        remote_job = JobRecord(
            url="https://example.com/job/2",
            source="RemoteOK",
            company="TestCo",
            title="Site Reliability Engineer",
            location="Remote",
        )
        assert passes_title_location(remote_job) is True
    finally:
        config.SHORTLISTR_ROOT = original
