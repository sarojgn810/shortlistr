"""Wake-phrase matching for voice mode.

"Shortlistr" is a coined word with a dropped vowel, so Whisper never renders it
one way. It guesses at real words: "short lister", "shortlist er", "Shortlist,
er". The matcher has to accept that spread while staying tight enough that
ordinary speech containing "shortlist" does not fire a command.
"""

from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))


# Whisper renderings collected from the way it handles coined names: it splits
# the compound, guesses a real suffix, and punctuates the seam.
@pytest.mark.parametrize(
    "heard",
    [
        "hey shortlistr what's my status",
        "Hey Shortlistr, what's my status?",
        "hey shortlister what's my status",
        "hey short lister what's my status",
        "hey short list er what's my status",
        "Hey Shortlist, er, what's my status",
        "hi shortlistr what's my status",
        "ok shortlistr what's my status",
        "okay short lister what's my status",
        "shortlistr what's my status",
        "HEY SHORTLISTR WHAT'S MY STATUS",
    ],
)
def test_wakes_on_mangled_renderings(heard):
    from voice.wake import match_wake

    woke, remainder = match_wake(heard)
    assert woke, f"should have woken on {heard!r}"
    assert "status" in remainder


# Captured from faster-whisper transcribing real synthesised speech, not
# guessed. The first two are why the matcher tolerates "he"/"shot" at all: the
# invented fixtures above all assumed Whisper would at least hear two words that
# sound like "short" and "list", and it does not.
@pytest.mark.parametrize(
    "heard,expected",
    [
        ("He shot Lister, what's my status?", "what's my status"),
        ("Hey short list of scan for jobs.", "scan for jobs"),
        ("Hey short list, open my tracker.", "open my tracker"),
        # This one reached a user as total silence: it did not wake, so nothing
        # was spoken, which is indistinguishable from broken audio.
        ("A short list of what is the status?", "what is the status"),
        # With "Shortlistr" supplied to the decoder as a hotword, the name comes
        # back intact and only the greeting varies.
        ("He Shortlistr, what is the status?", "what is the status"),
        ("Here's Shortlistr, Open My Tracker", "open my tracker"),
    ],
)
def test_wakes_on_transcripts_whisper_actually_produced(heard, expected):
    from voice.wake import match_wake

    woke, remainder = match_wake(heard)
    assert woke, f"real transcript did not wake: {heard!r}"
    assert remainder == expected


def test_strips_the_wake_phrase_from_the_command():
    from voice.wake import match_wake

    woke, remainder = match_wake("Hey Shortlistr, scan for jobs")
    assert woke
    # The remainder is what gets routed, so the wake phrase must be gone —
    # otherwise every intent pattern needs to tolerate a greeting prefix.
    assert remainder == "scan for jobs"


def test_bare_wake_phrase_wakes_with_empty_remainder():
    from voice.wake import match_wake

    for heard in ("Hey Shortlistr", "hey short lister", "shortlistr?"):
        woke, remainder = match_wake(heard)
        assert woke, heard
        assert remainder == ""


# The mic is hot for the whole session, so anything said near the laptop reaches
# this function. Firing a command on these would be the feature's worst failure.
@pytest.mark.parametrize(
    "heard",
    [
        "I shortlisted three roles today",
        "my shortlist is getting long",
        "can you add that to the shortlist",
        "she was shortlisted for the role",
        "the shortlisting process took a week",
        "",
        "   ",
        "so anyway I told him it was fine",
    ],
)
def test_does_not_wake_on_ordinary_speech(heard):
    from voice.wake import match_wake

    woke, _ = match_wake(heard)
    assert not woke, f"should NOT have woken on {heard!r}"


def test_wake_phrase_must_lead_the_utterance():
    from voice.wake import match_wake

    # Mid-sentence mentions are talk *about* the app, not talk *to* it.
    woke, _ = match_wake("I was telling Priya that hey shortlistr is useful")
    assert not woke


def test_follow_up_skips_the_wake_phrase():
    from voice.wake import match_wake

    # Inside the follow-up window the HUD passes woken=True, so a bare command
    # routes as-is. Without this, triage means saying the wake phrase 50 times.
    woke, remainder = match_wake("approve this one", woken=True)
    assert woke
    assert remainder == "approve this one"


def test_follow_up_still_tolerates_the_wake_phrase():
    from voice.wake import match_wake

    # Saying it anyway inside the window must not leave the phrase in the
    # command text, or the intent router sees "hey shortlistr approve this one".
    woke, remainder = match_wake("hey shortlistr approve this one", woken=True)
    assert woke
    assert remainder == "approve this one"
