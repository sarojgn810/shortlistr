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
    # City prefs also infer the country for geo-scoped remote.
    assert "india" in locs


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
        assert config.REMOTE_GEO_SCOPED is False
        assert config.REMOTE_GEO_KEYWORDS == []
    finally:
        config.SHORTLISTR_ROOT = original


def test_not_remote_strict_when_city_included(tmp_path):
    _write_profile(str(tmp_path), locations=["Bangalore", "Remote"])
    original = config.SHORTLISTR_ROOT
    try:
        config.SHORTLISTR_ROOT = str(tmp_path)
        config.reload_discovery_config()
        assert config.REMOTE_STRICT is False
        assert config.REMOTE_GEO_SCOPED is True
        assert "india" in config.REMOTE_GEO_KEYWORDS
        assert "bangalore" in config.REMOTE_GEO_KEYWORDS
    finally:
        config.AUTOJOB_ROOT = original


def test_remote_india_chip_expands(tmp_path):
    locs = _reload(tmp_path, locations=["Remote (India)"])
    assert "remote" in locs
    assert "india" in locs
    assert "ist" in locs
    original = config.AUTOJOB_ROOT
    try:
        config.AUTOJOB_ROOT = str(tmp_path)
        # _reload already called reload; re-check flags on current module state
        # after writing Remote (India) only — re-call reload to be sure
        config.reload_discovery_config()
        assert config.WANTS_REMOTE is True
        assert config.REMOTE_GEO_SCOPED is True
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


def test_blank_preferred_does_not_become_remote_only(tmp_path):
    """A user who never stated a location will take a job anywhere.

    LOCATION_KEYWORDS falls back to ["remote"] for query building. Reading that
    as a preference made the first scan reject every posting with a city in it,
    so the DB filled with thousands of off_target rows and Discover was empty.
    """
    from models.job import JobRecord
    from pipeline.filter import passes_title_location

    _write_profile(str(tmp_path), locations=[])
    original = config.SHORTLISTR_ROOT
    try:
        config.SHORTLISTR_ROOT = str(tmp_path)
        config.reload_discovery_config()
        assert config.LOCATION_PREFERENCE_SET is False
        assert config.REMOTE_STRICT is False

        city_job = JobRecord(
            url="https://example.com/job/3",
            source="Greenhouse",
            company="TestCo",
            title="Site Reliability Engineer",
            location="Hyderabad, India",
        )
        assert passes_title_location(city_job) is True
    finally:
        config.SHORTLISTR_ROOT = original


def test_stated_location_still_narrows(tmp_path):
    from models.job import JobRecord
    from pipeline.filter import passes_title_location

    _write_profile(str(tmp_path), locations=["Hyderabad"])
    original = config.SHORTLISTR_ROOT
    try:
        config.SHORTLISTR_ROOT = str(tmp_path)
        config.reload_discovery_config()
        assert config.LOCATION_PREFERENCE_SET is True

        def _job(location: str) -> JobRecord:
            return JobRecord(
                url=f"https://example.com/job/{location}",
                source="Greenhouse",
                company="TestCo",
                title="Site Reliability Engineer",
                location=location,
            )

        assert passes_title_location(_job("Hyderabad, India")) is True
        assert passes_title_location(_job("Berlin, Germany")) is False
        # A posting with no location at all stays in — it may still be a match.
        assert passes_title_location(_job("")) is True
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


def test_worldwide_remote_rejected_when_geo_scoped(tmp_path):
    """Bangalore + Remote must not accept bare worldwide Remote listings."""
    from models.job import JobRecord
    from pipeline.filter import passes_title_location

    _write_profile(str(tmp_path), locations=["Bangalore", "Remote"])
    original = config.SHORTLISTR_ROOT
    try:
        config.SHORTLISTR_ROOT = str(tmp_path)
        config.reload_discovery_config()

        def _job(location: str, source: str = "RemoteOK") -> JobRecord:
            return JobRecord(
                url=f"https://example.com/job/{location}",
                source=source,
                company="TestCo",
                title="Site Reliability Engineer",
                location=location,
            )

        # Aggregator bypass is gone — bare Remote / US-only fail.
        assert passes_title_location(_job("Remote")) is False
        assert passes_title_location(_job("Remote - United States")) is False
        assert passes_title_location(_job("Worldwide")) is False
        assert passes_title_location(_job("Anywhere")) is False
        # India / city signals pass.
        assert passes_title_location(_job("Remote - Bengaluru")) is True
        assert passes_title_location(_job("Remote, India")) is True
        assert passes_title_location(_job("Remote (IST)")) is True
        assert passes_title_location(_job("Bengaluru, India")) is True
    finally:
        config.AUTOJOB_ROOT = original


def test_remote_india_chip_accepts_india_remote(tmp_path):
    from models.job import JobRecord
    from pipeline.filter import passes_title_location

    _write_profile(str(tmp_path), locations=["Remote (India)"])
    original = config.AUTOJOB_ROOT
    try:
        config.AUTOJOB_ROOT = str(tmp_path)
        config.reload_discovery_config()

        def _job(location: str) -> JobRecord:
            return JobRecord(
                url=f"https://example.com/{location}",
                source="Remotive",
                company="Co",
                title="Site Reliability Engineer",
                location=location,
            )

        assert passes_title_location(_job("Remote, India")) is True
        assert passes_title_location(_job("Remote")) is False
        assert passes_title_location(_job("Remote - USA")) is False
    finally:
        config.AUTOJOB_ROOT = original


def test_bare_remote_still_accepts_worldwide(tmp_path):
    from models.job import JobRecord
    from pipeline.filter import passes_title_location

    _write_profile(str(tmp_path), locations=["Remote"])
    original = config.AUTOJOB_ROOT
    try:
        config.AUTOJOB_ROOT = str(tmp_path)
        config.reload_discovery_config()
        assert config.REMOTE_STRICT is True

        job = JobRecord(
            url="https://example.com/job/ww",
            source="RemoteOK",
            company="TestCo",
            title="Site Reliability Engineer",
            location="Remote",
        )
        assert passes_title_location(job) is True
    finally:
        config.SHORTLISTR_ROOT = original
