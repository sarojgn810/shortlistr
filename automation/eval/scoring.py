"""Turn a met/unmet requirement list into a score.

The evaluation prompt asks the model for two things: the posting's hard
requirements marked met or unmet against the CV with quoted evidence, and a
0-5 score that follows from that list. It is reliable at the first and hopeless
at the second — across 393 real evaluations, 175 came back as exactly 4.5, and
225 of them scored 4.5 or higher. Worse, the number was uncorrelated with fit:
postings discovery rated worst averaged 4.2 while those it rated best averaged
4.07.

So the model is left doing the reading, and the arithmetic happens here.

Counting met requirements alone is not enough either. In the same corpus, 116
of 248 evaluations had *every* requirement met, which is a 116-way tie at the
top — a job proving one requirement ranked level with one proving eleven. The
smoothing term below is what separates them: it treats a short requirement list
as weak evidence rather than as a perfect record.
"""

from __future__ import annotations

from typing import Any

MAX_SCORE = 5.0

# Laplace smoothing: pretend every posting starts with one met and one unmet
# requirement already on the board. A 1/1 record then reads as 2/3 rather than
# as perfection, while 11/11 reads as 12/13 — so depth of evidence is worth
# something and a single lucky requirement is not.
PRIOR_MET = 1.0
PRIOR_TOTAL = 2.0


def _usable(rows: Any) -> list[dict[str, Any]]:
    """Rows carrying an actual requirement. A malformed row is missing data, not a gap."""
    if not isinstance(rows, list):
        return []
    return [
        r for r in rows
        if isinstance(r, dict) and str(r.get("req") or "").strip()
    ]


def score_from_evidence(must_haves: Any) -> float | None:
    """Score 0-5 from met/unmet counts, or None when there is no evidence.

    None matters: an evaluation that listed no requirements knows nothing about
    the job. Scoring it 0.0 would rank it below a posting that genuinely fails
    everything, and 5.0 would float it to the top of the review queue. The
    caller decides what to do with an unknown — it must not be mistaken for a
    judgement.
    """
    rows = _usable(must_haves)
    if not rows:
        return None

    met = sum(1 for r in rows if r.get("met"))
    ratio = (met + PRIOR_MET) / (len(rows) + PRIOR_TOTAL)
    return round(max(0.0, min(1.0, ratio)) * MAX_SCORE, 1)


def evidence_summary(must_haves: Any) -> tuple[int, int]:
    """``(met, total)`` — what the score is made of, for showing your work."""
    rows = _usable(must_haves)
    return sum(1 for r in rows if r.get("met")), len(rows)


def unmet_requirements(must_haves: Any) -> list[str]:
    """The gaps, in order — the part a cover letter has to answer."""
    return [str(r.get("req")) for r in _usable(must_haves) if not r.get("met")]
