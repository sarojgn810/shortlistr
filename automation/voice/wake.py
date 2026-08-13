"""Wake-phrase detection for voice mode.

The session mic is click-gated and every speech segment is already transcribed
locally, so waking is a text check on the transcript — no second always-on
model, no access key, no extra download.

Two things make this harder than a string compare:

*Whisper never spells "Shortlistr" the same way twice.* It is a coined word with
a dropped vowel, so the model reaches for real words it knows: "short lister",
"shortlist er", "Shortlist, er". All of those have to wake.

*The mic hears the whole room.* Anything said near the laptop reaches this
function, so "I shortlisted three roles today" must not fire a command. That is
why the phrase has to lead the utterance and why a bare "shortlist" — with no
``-r``/``-er`` and no greeting — is not enough on its own.
"""

from __future__ import annotations

import re

# Keep apostrophes: stripping them turns "what's my status" into "what s my
# status", which every downstream intent pattern would then have to tolerate.
_PUNCT = re.compile(r"[^\w\s']")
_SPACES = re.compile(r"\s+")

# The greeting is whatever Whisper made of "hey" — observed: "hey", "he",
# "here's", "a". Enumerating them was a treadmill; the decoder is now given
# "Shortlistr" as a hotword (see stt.WAKE_HOTWORD) so the *name* is the reliable
# token and the greeting no longer has to carry the decision.
_GREETING = r"(?:hey|hay|he|here'?s|hi|hello|ok|okay|yo|a|uh)"
# "short" is heard as "shot" about as often as itself; "short" and "list" may be
# split or joined; the tail may be -r, -er or absent. Written out: shortlistr,
# shortlister, short lister, shot lister, shortlist er.
_NAME = r"shor?t\s*list\s*(?:er|r)"

# Three ways in, loosest last:
#
# 1. A known greeting, then the name with the tail optional — "hey short list".
# 2. The name alone, tail required — "shortlistr, what's my status".
# 3. Up to two unrecognised lead-in words, then the name *with* its tail. This
#    is what catches greetings nobody predicted. The tail is what keeps it
#    honest: "my shortlist is getting long" has no -r, so it cannot wake.
#
# A missed wake looks like a totally broken feature; a spurious one costs a
# shrug and an "I didn't catch that". The asymmetry is why these lean open.
_WITH_GREETING = re.compile(rf"^{_GREETING}\s+shor?t\s*list\s*(?:er|r)?\b")
_BARE = re.compile(rf"^{_NAME}\b")
_LEAD_IN = re.compile(rf"^(?:\S+\s+){{1,2}}?{_NAME}\b")

# Debris from the name's own tail, mis-split onto the command: "Hey short list
# OF scan for jobs". Only a single leading connector, and never a word that
# could begin a real command.
_TAIL_DEBRIS = re.compile(r"^(?:of|a|er|uh|r|is|it)\s+")


def normalize(text: str) -> str:
    """Lowercase, drop sentence punctuation, collapse runs of whitespace."""
    return _SPACES.sub(" ", _PUNCT.sub(" ", (text or "").lower())).strip()


def match_wake(text: str, *, woken: bool = False) -> tuple[bool, str]:
    """Return ``(woke, remainder)`` for a transcribed utterance.

    ``remainder`` is the command with the wake phrase removed — the intent
    router should never have to know a greeting might be sitting in front of it.

    ``woken=True`` is the follow-up window: the caller already has an open
    exchange, so a bare command counts. The phrase is still stripped when
    present, since saying it again is natural and must not leak into the text.
    """
    norm = normalize(text)
    for pattern in (_WITH_GREETING, _BARE, _LEAD_IN):
        m = pattern.match(norm)
        if m:
            return True, _TAIL_DEBRIS.sub("", norm[m.end() :].strip())
    return (True, norm) if woken else (False, "")
