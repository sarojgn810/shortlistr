"""Scoring from evidence rather than from the model's own number.

The model was asked to list each hard requirement, mark it met or unmet against
the CV, and then produce a 0-5 score that followed that list. It did the first
part well and the second part not at all: across 393 real evaluations, 175 came
back as exactly 4.5 and 225 scored 4.5 or higher. The number did not track fit
either — jobs discovery rated worst averaged a *higher* eval score (4.2) than
jobs it rated best (4.07).

So the number is computed here instead, from the list the model is good at.
"""

from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))


def req(met: bool, name: str = "Kubernetes"):
    return {"req": name, "met": met, "evidence": "ran EKS in prod" if met else ""}


def test_all_met_beats_some_met():
    from eval.scoring import score_from_evidence

    assert score_from_evidence([req(True)] * 5) > score_from_evidence([req(True)] * 3 + [req(False)] * 2)


def test_none_met_scores_near_zero():
    from eval.scoring import score_from_evidence

    assert score_from_evidence([req(False)] * 4) < 1.0


def test_depth_of_evidence_breaks_the_tie():
    from eval.scoring import score_from_evidence

    # This is the whole point. 116 of 248 real evaluations had every must-have
    # met, so "all met" alone left a 116-way tie at the top. Proving eleven
    # requirements is stronger evidence than proving one.
    deep = score_from_evidence([req(True)] * 11)
    shallow = score_from_evidence([req(True)] * 1)

    assert deep > shallow
    # Real pair from the data: TCS Site Reliability Engineer (11/11) versus
    # DataFortis MLOps Engineer (1/1). They scored identically before.
    assert deep - shallow > 1.0


def test_more_unmet_always_scores_lower():
    from eval.scoring import score_from_evidence

    previous = 6.0
    for unmet in range(0, 7):
        current = score_from_evidence([req(True)] * (6 - unmet) + [req(False)] * unmet)
        assert current < previous, f"{unmet} unmet did not lower the score"
        previous = current


def test_stays_in_range():
    from eval.scoring import score_from_evidence

    assert 0.0 <= score_from_evidence([req(False)] * 25) <= 5.0
    assert 0.0 <= score_from_evidence([req(True)] * 25) <= 5.0


def test_no_evidence_returns_none_rather_than_a_confident_zero():
    from eval.scoring import score_from_evidence

    # An eval with no requirements listed knows nothing. Scoring it 0.0 would
    # rank it below a job that genuinely fails every requirement, and scoring
    # it 5.0 would float it to the top of the queue.
    assert score_from_evidence([]) is None
    assert score_from_evidence(None) is None


def test_produces_a_spread_across_realistic_shapes():
    from eval.scoring import score_from_evidence

    shapes = [(m, t) for t in range(1, 12) for m in range(0, t + 1)]
    scores = {score_from_evidence([req(True)] * m + [req(False)] * (t - m)) for m, t in shapes}

    # The failure being fixed was three values covering 65% of the corpus.
    assert len(scores) > 20, f"only {len(scores)} distinct scores"


def test_top_band_is_selective():
    from eval.scoring import score_from_evidence

    # Nothing should reach the top band on thin evidence: 47% of the corpus
    # scored >= 4.5 before, which is not a shortlist.
    assert score_from_evidence([req(True)] * 3) < 4.5
    assert score_from_evidence([req(True)] * 9) >= 4.5


@pytest.mark.parametrize("bad", [[{"req": "", "met": True}], [{"met": True}], ["nonsense"]])
def test_ignores_malformed_rows(bad):
    from eval.scoring import score_from_evidence

    # A malformed row is missing information, not a failed requirement.
    assert score_from_evidence(bad) is None
