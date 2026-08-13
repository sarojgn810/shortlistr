"""Intent routing for voice mode.

Two properties matter more than breadth of coverage here:

*Precedence.* An open offer ("evaluate it, or shall I prep?") has to claim the
one-word answer that follows, or the agent stops being a conversation.

*Conservatism.* A miss costs a second of LLM latency; a wrong match takes an
action the user did not ask for. Every ambiguous phrasing should fall through.
"""

from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))

JOB = "a1b2c3d4"


# ── Offers claim the reply ────────────────────────────────────────────────────

def test_offer_claims_a_one_word_answer():
    from voice.intents import resolve

    offer = {"job_id": JOB, "options": ["evaluate", "apply", "skip"]}
    intent = resolve("evaluate", offer=offer)
    assert intent.kind == "tool"
    assert intent.tool == "shortlistr.evaluate"
    # The job comes from the offer, never from speech — Whisper cannot be
    # trusted to reproduce a company name or an 8-character id.
    assert intent.args["job_id"] == JOB


def test_offer_beats_a_general_intent_of_the_same_name():
    from voice.intents import resolve

    # Bare "skip" with no offer is a triage move against the cursor; with an
    # offer open it must act on the offered job instead.
    assert resolve("skip").kind == "triage"

    offer = {"job_id": JOB, "options": ["evaluate", "apply", "skip"]}
    intent = resolve("skip", offer=offer)
    assert intent.kind == "tool"
    assert intent.tool == "shortlistr.skip"
    assert intent.args["job_id"] == JOB


def test_offer_only_claims_its_own_options():
    from voice.intents import resolve

    offer = {"job_id": JOB, "options": ["evaluate", "apply"]}
    # "reports" was never offered, so it routes normally rather than being
    # forced into the offer.
    assert resolve("open reports", offer=offer).kind == "nav"


def test_ambiguous_yes_does_not_pick_an_offer_option():
    from voice.intents import resolve

    offer = {"job_id": JOB, "options": ["evaluate", "apply"]}
    # "Evaluate it, or shall I prep?" — "yes" answers neither. Guessing here
    # would run a write action the user did not choose.
    intent = resolve("yes", offer=offer)
    assert intent.kind == "clarify"


# ── Tools ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "heard",
    [
        "what's my status",
        "status",
        "how am i doing",
        "umm what's my, uh, status",       # filler — VAD captures thinking noises
        "WHAT'S MY STATUS",                # some Whisper builds emit all caps
        "what's my status",
    ],
)
def test_status_variants(heard):
    from voice.intents import resolve

    intent = resolve(heard)
    assert intent.kind == "tool"
    assert intent.tool == "shortlistr.status"
    assert intent.duration == "instant"


def test_inbox_question_is_a_tool_not_navigation():
    from voice.intents import resolve

    intent = resolve("what's in my inbox")
    assert intent.kind == "tool"
    assert intent.tool == "shortlistr.list_jobs"
    assert intent.args["status"] == "inbox"


def test_pipeline_question_reads_the_evaluated_list():
    from voice.intents import resolve

    intent = resolve("how many are in the pipeline")
    assert intent.kind == "tool"
    assert intent.tool == "shortlistr.list_jobs"
    assert intent.args["status"] == "evaluated"


def test_job_scoped_intent_uses_the_current_job():
    from voice.intents import resolve

    intent = resolve("tell me more about this one", job_id=JOB)
    assert intent.kind == "tool"
    assert intent.tool == "shortlistr.explain"
    assert intent.args["job_id"] == JOB


def test_job_scoped_intent_without_a_job_asks_rather_than_guessing():
    from voice.intents import resolve

    intent = resolve("prep an application for this one")
    assert intent.kind == "clarify"
    assert intent.speech


# ── Long operations ───────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "heard", ["scan for jobs", "run discovery", "find me some jobs", "search for new roles"]
)
def test_discovery_enqueues_rather_than_blocking(heard):
    from voice.intents import resolve

    intent = resolve(heard)
    # dispatch._discover runs run_scheduled_scan() inline for 2.5-8.5 minutes and
    # the dashboard client times out at 90s, so voice must never call the tool.
    assert intent.kind == "enqueue"
    assert intent.tool != "shortlistr.discover"
    assert intent.duration == "minutes"


def test_slow_tools_are_marked_so_the_agent_can_warn():
    from voice.intents import resolve

    assert resolve("evaluate this one", job_id=JOB).duration == "seconds"
    assert resolve("prep this one", job_id=JOB).duration == "seconds"


# ── Navigation ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "heard,route",
    [
        ("open my tracker", "/tracker"),
        ("go to prep", "/prep"),
        ("show me the pipeline", "/pipeline"),
        ("take me to connections", "/connections"),
        ("open reports", "/reports"),
        ("go to my resume", "/cv"),
        ("umm, open my, uh, tracker", "/tracker"),
    ],
)
def test_navigation(heard, route):
    from voice.intents import resolve

    intent = resolve(heard)
    assert intent.kind == "nav"
    assert intent.route == route
    assert intent.duration == "instant"


# ── Triage ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "heard,action",
    [
        ("next", "next"),
        ("next one", "next"),
        ("approve", "approve"),
        ("approve this one", "approve"),
        ("skip", "skip"),
        ("start triage", "start"),
        ("stop telling me about jobs", "mute"),
    ],
)
def test_triage_moves(heard, action):
    from voice.intents import resolve

    intent = resolve(heard)
    assert intent.kind == "triage"
    assert intent.action == action


# ── Falling through ───────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "heard",
    [
        "how's the search going this week",
        "what did i apply to at acme",
        "why did you score that one so low",
        "tell me about the company culture there",
        "should i be worried about the salary band",
        "what do you think of my resume",
        "",
    ],
)
def test_open_questions_fall_through_to_the_llm(heard):
    from voice.intents import resolve

    # A miss costs a second of latency. A wrong match takes an action.
    assert resolve(heard).kind == "miss"


def test_apply_is_gated_not_matched_away():
    from voice.intents import resolve

    intent = resolve("apply to this one", job_id=JOB)
    assert intent.kind == "tool"
    assert intent.tool == "shortlistr.apply_assist"
    # Routing does not decide authorization — dispatch.call_tool does.
    assert intent.args["job_id"] == JOB
