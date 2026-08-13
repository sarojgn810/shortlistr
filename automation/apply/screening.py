"""Answers to ATS screening questions, drawn from the profile and the CV.

These end up on a real job application under the user's name, so the rule
throughout is: **an unanswered question is fine, a wrong one is not.** A blank
field costs a moment of typing. A claim of experience the user does not have
can cost them a rescinded offer, and it misrepresents them to an employer who
asked in good faith.

Every answer therefore traces to something the user wrote themselves — a
setting in `config/profile.yml`, or a term that appears in `cv.md`. Where
neither speaks, this returns ``None`` and the field is left for the human.

Two deliberate silences:

*Absence of evidence is not "No".* A CV is a highlight reel, not an exhaustive
record. Not finding "Kafka" means we do not know, not that the user has never
used it — so unmatched experience questions go unanswered rather than answered
negatively.

*Demographic questions are never answered.* Gender, ethnicity, veteran and
disability fields are voluntary. They belong to the user, and a tool filling
them in is speaking for them about protected characteristics.
"""

from __future__ import annotations

import re
from typing import Any

# Voluntary EEO / demographic fields. Matched first, and always declined.
_DEMOGRAPHIC = re.compile(
    r"\bgender\b|\bsex\b|hispanic|latino|\brace\b|ethnic|veteran|disab|"
    r"protected\s+(class|characteristic)|LGBT|transgender|pronoun",
    re.I,
)

# Question → the profile key that answers it. Order matters: the first match
# wins, so narrower patterns come first.
_PROFILE_QUESTIONS: list[tuple[str, str]] = [
    (r"require\s+(visa\s+)?sponsor|need\s+sponsor|sponsorship\s+for\s+employment",
     "work_authorization"),
    (r"legally\s+authoriz|authorized\s+to\s+work|eligible\s+to\s+work|work\s+authoriz",
     "work_authorization"),
    (r"previously\s+worked|worked\s+at\s+or\s+consulted|former\s+employee|"
     r"ever\s+been\s+employed\s+by",
     "worked_here_before"),
    (r"on[-\s]?call\s+rotation|comfortable\s+.*on[-\s]?call|participate\s+in\s+.*on[-\s]?call",
     "on_call_ok"),
    # "…the country in which you will be located if hired" is the same question
    # as "country of residence", asked the long way round.
    (r"country\s+of\s+residence|country\s+.*\bresid|which\s+country|country\s+"
     r"in\s+which|country\s+.*\b(based|located|work(ing)?\s+from)",
     "country_of_residence"),
    (r"willing\s+to\s+relocat|open\s+to\s+relocat|relocation", "willing_to_relocate"),
    (r"notice\s+period|availability\s+to\s+join|when\s+can\s+you\s+(join|start)",
     "notice_period"),
    (r"years\s+of\s+experience|how\s+many\s+years|total\s+experience", "years_exp"),
    (r"current\s+(ctc|salary|compensation)|present\s+ctc", "current_ctc"),
    (r"expected\s+(ctc|salary|compensation)|desired\s+salary|salary\s+expectation",
     "expected_ctc"),
    (r"how\s+did\s+you\s+hear|how\s+do\s+you\s+know|referral\s+source", "how_heard"),
    (r"current\s+location|where\s+are\s+you\s+(based|located)|^location", "location"),
]

# "Do you have experience with X" — X is looked up in the CV.
_EXPERIENCE_QUESTION = re.compile(
    r"(?:hands[-\s]?on|production|professional|practical|working)?\s*"
    r"experience\s+(?:in|with|using|of)\s+(.+)$",
    re.I,
)

# Sponsorship phrasing is inverted: "no sponsorship required" answers "will you
# require sponsorship?" with No, and "authorized to work?" with Yes.
_NEEDS_SPONSORSHIP = re.compile(r"\bno\s+sponsorship|not?\s+require\s+sponsor|"
                                r"without\s+sponsorship|authorized", re.I)


def _country_from_location(location: str) -> str:
    """Last part of "Bangalore, India". Empty when there is no comma to trust."""
    parts = [p.strip() for p in (location or "").split(",") if p.strip()]
    return parts[-1] if len(parts) > 1 else ""


def _yes_no(value: str) -> str | None:
    """Read an explicit yes/no out of a profile value."""
    low = value.strip().lower()
    if low.startswith(("yes", "y ", "true")):
        return "Yes"
    if low.startswith(("no", "n ", "false")):
        return "No"
    return None


def _sponsorship_answer(question: str, stated: str) -> str | None:
    """Answer sponsorship and authorisation from one free-text profile line."""
    self_sufficient = bool(_NEEDS_SPONSORSHIP.search(stated))
    asks_for_sponsorship = bool(re.search(r"sponsor", question, re.I))
    if asks_for_sponsorship:
        return "No" if self_sufficient else "Yes"
    # "Are you legally authorized to work…"
    return "Yes" if self_sufficient else None


# Postings and CVs rarely use the same spelling for the same thing. A CV saying
# "Go" does not stop being evidence because the question said "Golang".
_SYNONYMS: dict[str, tuple[str, ...]] = {
    "golang": ("go",),
    "go": ("golang",),
    "k8s": ("kubernetes",),
    "kubernetes": ("k8s",),
    "gcp": ("google cloud", "google cloud platform"),
    "google cloud": ("gcp",),
    "aws": ("amazon web services",),
    "amazon web services": ("aws",),
    "postgres": ("postgresql",),
    "postgresql": ("postgres",),
    "javascript": ("js",),
    "ci/cd": ("cicd", "ci cd", "continuous integration"),
    "cicd": ("ci/cd", "continuous integration"),
    "iac": ("infrastructure as code", "terraform"),
    "observability": ("prometheus", "grafana", "monitoring"),
}


def _cv_mentions(term: str, cv_text: str) -> bool:
    """Whole-word-ish match, so "Go" does not match "Google". Follows synonyms."""
    term = term.strip()
    if len(term) < 2:
        return False

    for candidate in (term, *_SYNONYMS.get(term.lower(), ())):
        pattern = rf"(?<![\w+#]){re.escape(candidate)}(?![\w+#])"
        if re.search(pattern, cv_text, re.I):
            return True
    return False


def _experience_answer(question: str, cv_text: str) -> str | None:
    """Yes only when the CV names the technology asked about."""
    match = _EXPERIENCE_QUESTION.search(question)
    if not match or not cv_text:
        return None

    tail = match.group(1)
    # "Kubernetes or Mesos?" / "AWS, GCP and Azure" — any one is enough.
    candidates = [t.strip(" ?.*:;") for t in re.split(r"\bor\b|\band\b|,|/", tail)]
    for term in candidates:
        # Trim trailing prose: "AWS infrastructure at scale" -> try the phrase,
        # then its leading token.
        for probe in (term, term.split()[0] if term.split() else ""):
            if probe and _cv_mentions(probe, cv_text):
                return "Yes"
    return None


def answer_for(question: str, profile: dict[str, Any], cv_text: str = "") -> str | None:
    """Best answer for a screening question, or None to leave it to the user."""
    text = (question or "").strip()
    if not text:
        return None

    if _DEMOGRAPHIC.search(text):
        return None

    for pattern, key in _PROFILE_QUESTIONS:
        if not re.search(pattern, text, re.I):
            continue
        stated = str(profile.get(key) or "").strip()
        if not stated and key == "country_of_residence":
            # "Bangalore, India" already says the country. Reading it off the
            # location the user set is not a guess about them; asking them to
            # type the same fact twice is just friction.
            stated = _country_from_location(str(profile.get("location") or ""))
        if not stated:
            return None
        if key == "work_authorization":
            return _sponsorship_answer(text, stated)
        return _yes_no(stated) or stated

    return _experience_answer(text, cv_text)
