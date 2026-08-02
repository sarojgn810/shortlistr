"""Contact-resolution layer unit tests (no live SERP/Hunter)."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "automation"))

from contacts.pattern import generate_emails, learn_pattern  # noqa: E402
from contacts.score import decision_for, final_score, map_verify_status  # noqa: E402
from contacts.person_discover import mine_jd_people, mine_ats_people  # noqa: E402
from contacts.domain import normalize_host, guess_catch_all  # noqa: E402


def test_learn_first_dot_last_pattern():
    known = [
        ("jane", "doe", "jane.doe@acme.com"),
        ("john", "smith", "john.smith@acme.com"),
    ]
    pat, conf, n = learn_pattern(known)
    assert pat == "{first}.{last}"
    assert conf == 1.0
    assert n == 2
    emails = generate_emails("Ada", "Lovelace", "acme.com", pattern=pat)
    assert emails[0][0] == "ada.lovelace@acme.com"


def test_generate_emails_skips_single_token_and_trailing_dot():
    """GitHub logins / company slugs must not become entrupy.@domain.com."""
    assert generate_emails("entrupy", "", "entrupy.com", pattern="{first}.{last}") == []
    assert generate_emails("entrupy-interview", "", "entrupy.com") == []
    from contacts.pattern import apply_pattern

    assert apply_pattern("{first}.{last}", "entrupy", "") == ""
    assert apply_pattern("{first}.{last}", "ada", "lovelace") == "ada.lovelace"


def test_scoring_and_seg_gate():
    score = final_score(0.9, "valid", 2, 0.85)
    assert score >= 0.8
    assert decision_for(score, verify_status="valid") == "SEND_NOW"
    # Proofpoint → REVIEW even at high score
    assert (
        decision_for(0.85, verify_status="accept_all", mx_provider="proofpoint")
        == "REVIEW"
    )
    assert map_verify_status("risky", mx_provider="mimecast") == "accept_all"
    assert guess_catch_all("proofpoint") == 1


def test_mine_jd_and_ats():
    jd = "Contact: Priya Sharma — priya.sharma@example.com for questions."
    people = mine_jd_people(jd, "https://jobs.example.com/x", company="Example")
    assert any("priya" in (p.get("email") or "").lower() or "Priya" in (p.get("full_name") or "") for p in people)

    job = {
        "metadata": {
            "recruiter": {"name": "Alex Recruiter", "email": "alex@tt.co", "title": "TA"}
        }
    }
    ats = mine_ats_people(job)
    assert ats and ats[0]["email"] == "alex@tt.co"
    assert ats[0]["source"] == "ats_field"
    assert normalize_host("https://www.Stripe.com/careers") == "stripe.com"
