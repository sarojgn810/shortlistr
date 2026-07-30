"""Unit tests for the pipeline + application state machines (store/status.py).

Exercise the transition rules in isolation (no DB) so a broken transition map is caught
directly, not only via API integration. Complements test_j1.py's end-to-end coverage.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "automation"))

import pytest

from store.status import (
    APPLICATION_TRANSITIONS,
    PIPELINE_STATUSES,
    PIPELINE_TRANSITIONS,
    StatusError,
    _assert_application_transition,
    _assert_pipeline_transition,
    _normalize_pipeline_status,
    validate_job_id,
)


# ── pipeline transitions ─────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "cur,new",
    [
        ("pending", "evaluated"),
        ("pending", "skipped"),
        ("evaluated", "approved"),
        ("evaluated", "skipped"),
        ("evaluated", "pending"),   # undo
        ("approved", "submitted"),
        ("approved", "skipped"),
        ("approved", "evaluated"),  # undo
        ("skipped", "pending"),     # un-skip
    ],
)
def test_valid_pipeline_transitions(cur, new):
    _assert_pipeline_transition(cur, new)  # must not raise


@pytest.mark.parametrize(
    "cur,new",
    [
        ("pending", "approved"),    # must evaluate first
        ("pending", "submitted"),
        ("evaluated", "submitted"),  # must approve first
        ("submitted", "approved"),   # terminal
        ("submitted", "pending"),
        ("skipped", "approved"),     # skipped only returns to pending
    ],
)
def test_invalid_pipeline_transitions(cur, new):
    with pytest.raises(StatusError):
        _assert_pipeline_transition(cur, new)


def test_submitted_is_terminal():
    assert PIPELINE_TRANSITIONS["submitted"] == frozenset()


def test_every_pipeline_status_has_a_transition_entry():
    # Guards against a status existing with no rule (the "two enforcement points
    # must agree" landmine — every reachable state needs an explicit map entry).
    for s in PIPELINE_STATUSES:
        assert s in PIPELINE_TRANSITIONS


# ── application transitions ──────────────────────────────────────────────────
@pytest.mark.parametrize(
    "cur,new",
    [
        ("evaluated", "applied"),
        ("applied", "responded"),
        ("applied", "interview"),
        ("applied", "rejected"),
        ("responded", "interview"),
        ("interview", "offer"),
        ("interview", "rejected"),
        ("skip", "evaluated"),  # skip is reversible
        ("skip", "applied"),
    ],
)
def test_valid_application_transitions(cur, new):
    _assert_application_transition(cur, new)  # must not raise


@pytest.mark.parametrize(
    "cur,new",
    [
        ("evaluated", "offer"),  # can't jump straight to offer
        ("applied", "offer"),    # must interview first
        ("rejected", "applied"),  # terminal
        ("offer", "applied"),    # offer only -> discarded
    ],
)
def test_invalid_application_transitions(cur, new):
    with pytest.raises(StatusError):
        _assert_application_transition(cur, new)


def test_application_same_state_is_noop():
    _assert_application_transition("applied", "applied")  # must not raise


def test_skip_is_reversible():
    assert "evaluated" in APPLICATION_TRANSITIONS["skip"]
    assert "applied" in APPLICATION_TRANSITIONS["skip"]


def test_terminal_application_states():
    assert APPLICATION_TRANSITIONS["rejected"] == frozenset()
    assert APPLICATION_TRANSITIONS["discarded"] == frozenset()


# ── job id + status normalization ────────────────────────────────────────────
def test_validate_job_id_accepts_16_hex_lowercased():
    assert validate_job_id("ABCDEF0123456789") == "abcdef0123456789"


@pytest.mark.parametrize("bad", ["", "xyz", "123", "g" * 16, "abc", "0123456789abcdef0"])
def test_validate_job_id_rejects_bad(bad):
    with pytest.raises(StatusError):
        validate_job_id(bad)


def test_normalize_pipeline_status():
    assert _normalize_pipeline_status("APPROVED") == "approved"
    with pytest.raises(StatusError):
        _normalize_pipeline_status("bogus")
