"""Lists the UI keys by value must not contain duplicates.

Regression: the profile carried "AI Operations Engineer" twice, and the profile
page keys title chips by the title string — React threw "Encountered two children
with the same key". Skill chips have the same shape, and boards do repeat skills.
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))


# ── Profile titles / locations ───────────────────────────────────────────────

def test_parse_titles_drops_repeats_keeping_first_spelling():
    from profile_store import _parse_titles

    assert _parse_titles([
        "AI Operations Engineer",
        "SRE",
        "AI Operations Engineer",
        "ai operations engineer",
    ]) == ["AI Operations Engineer", "SRE"]


def test_parse_titles_dedupes_comma_input():
    from profile_store import _parse_titles

    assert _parse_titles("SRE, MLOps Engineer, SRE") == ["SRE", "MLOps Engineer"]


def test_profile_read_dedupes_a_hand_edited_file(monkeypatch, tmp_path):
    """profile.yml is user-editable, so the read path must tolerate repeats."""
    import profile_store

    profile = tmp_path / "profile.yml"
    profile.write_text(
        "candidate:\n"
        "  name: Test User\n"
        "  email: test@example.com\n"
        "filters:\n"
        "  target_titles:\n"
        '    - "AIOps Engineer"\n'
        '    - "AIOps Engineer"\n'
        "  preferred_locations:\n"
        '    - "Bangalore"\n'
        '    - "Bangalore"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(profile_store, "PROFILE_PATH", str(profile))

    ui = profile_store.get_profile_for_ui()
    assert ui["target_titles"] == ["AIOps Engineer"]
    assert ui["preferred_locations"] == ["Bangalore"]


# ── Job skills ───────────────────────────────────────────────────────────────

def test_dedupe_skills_is_case_insensitive_and_ordered():
    from api.jobs_api import dedupe_skills

    assert dedupe_skills(["Python", "AWS", "python", " aws ", "Kubernetes"]) == [
        "Python",
        "AWS",
        "Kubernetes",
    ]


def test_parse_skills_dedupes_json_and_csv_shapes():
    from api.jobs_api import _parse_skills

    assert _parse_skills('["Python", "Python", "Terraform"]') == ["Python", "Terraform"]
    assert _parse_skills("Python, Python , Terraform") == ["Python", "Terraform"]


def test_dedupe_skills_respects_limit():
    from api.jobs_api import dedupe_skills

    assert dedupe_skills([f"skill{i}" for i in range(20)], limit=8) == [
        f"skill{i}" for i in range(8)
    ]
