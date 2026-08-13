"""Spoken forms for tool results.

Everything here exists because a screen and a speaker want opposite things. The
dashboard can show an id, a URL and a score column; read aloud those are noise
at best. A brief is company, title, score, one distinguishing fact — then an
offer, so the user always has something to answer.

The templates are deterministic on purpose: free, instant, and structurally
incapable of reading an id out loud.
"""

from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))

JOB = {
    "id": "a1b2c3d4",
    "company": "Stripe",
    "title": "Senior Site Reliability Engineer",
    "score": 4.2,
    "location": "Bangalore",
    "url": "https://boards.greenhouse.io/stripe/jobs/1234567",
}


def test_job_brief_names_the_role_and_offers():
    from voice.speech_form import job_brief

    said = job_brief(JOB)
    assert "Stripe" in said
    assert "Site Reliability" in said
    assert said.rstrip().endswith("?"), "a brief must hand the turn back"


def test_job_brief_never_speaks_ids_or_urls():
    from voice.speech_form import job_brief

    said = job_brief(JOB)
    assert JOB["id"] not in said
    assert "http" not in said
    assert "greenhouse" not in said.lower()


def test_job_brief_stays_brief():
    from voice.speech_form import job_brief

    said = job_brief(JOB)
    # Two sentences plus a question. Longer than this and a three-job
    # announcement becomes a monologue nobody can interrupt.
    assert len(said) < 220, said


def test_job_brief_survives_missing_fields():
    from voice.speech_form import job_brief

    said = job_brief({"id": "x", "company": None, "title": "SRE", "score": None})
    assert said
    assert "None" not in said


def test_speech_is_free_of_markup():
    from voice.speech_form import for_speech

    said = for_speech("**Stripe** is hiring\n\n- Senior SRE\n- `k8s`\n\n[link](http://x.com)")
    for junk in ("*", "`", "[", "]", "(", "#", "http"):
        assert junk not in said, f"{junk!r} would be read aloud"


def test_status_snapshot_is_spoken_as_a_sentence():
    from voice.speech_form import status_brief

    said = status_brief({"pipeline": {"pending": 12, "approved": 3}})
    assert "12" in said
    assert "{" not in said and ":" not in said


def test_list_brief_counts_rather_than_enumerating():
    from voice.speech_form import list_brief

    jobs = [{"id": f"id{i}", "company": f"Co{i}", "title": "SRE"} for i in range(40)]
    said = list_brief(jobs, "inbox")
    assert "40" in said
    # Reading forty companies aloud is the failure mode this guards.
    assert "Co39" not in said
    assert len(said) < 200


def test_list_brief_handles_empty():
    from voice.speech_form import list_brief

    said = list_brief([], "inbox")
    assert said
    assert "0" not in said or "nothing" in said.lower()


def test_duration_acknowledgements_are_honest():
    from voice.speech_form import waiting_ack

    assert waiting_ack("instant") == ""
    assert "second" in waiting_ack("seconds")
    # A scan is 2.5-8.5 minutes. Saying "just a moment" would be a lie the user
    # discovers by waiting.
    assert "minute" in waiting_ack("minutes")


def test_no_job_id_leaks_through_any_formatter():
    from voice.speech_form import job_brief, list_brief, status_brief

    jobs = [dict(JOB)]
    for said in (job_brief(JOB), list_brief(jobs, "inbox"), status_brief({"pipeline": {}})):
        assert not re.search(r"\b[0-9a-f]{8,}\b", said), said
