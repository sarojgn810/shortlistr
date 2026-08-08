"""The seven public boards are fetched together, not one after another.

Walked in series, the source cost the sum of its worst members: WorkingNomads
alone took 7.5s to return 1 job, and five of the seven spent 13.5s between them
for 4 jobs, while RemoteOK and Remotive delivered 134 in 2.5s. They are seven
different hosts, so overlapping them adds no load on any one of them.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "automation"))


_BOARD_LABELS = ("Himalayas", "Remotive", "RemoteOK", "WeWorkRemotely",
                 "WorkingNomads", "NoDesk", "Jobspresso")


def _fake_boards(*, gate=None, failing: set[str] | None = None):
    failing = failing or set()

    def make(label: str):
        def fn():
            if gate:
                gate()
            if label in failing:
                raise RuntimeError(f"{label} is down")
            return [_Rec(f"https://x.test/{label}")]

        return fn

    return [(lbl, make(lbl)) for lbl in _BOARD_LABELS]


class _Rec:
    def __init__(self, url):
        self.url = url


def test_boards_are_fetched_concurrently(monkeypatch, overlap_gate):
    from sources.adapters.aggregators_adapter import AggregatorsAdapter

    # parallel_call pools at min(10, len(fns)), so all seven run together.
    gate, ran_alone = overlap_gate(len(_BOARD_LABELS))
    boards = _fake_boards(gate=gate)
    monkeypatch.setattr(AggregatorsAdapter, "BOARDS", boards)

    jobs, stats = AggregatorsAdapter().fetch_raw()

    assert not ran_alone.is_set(), "boards were fetched one at a time"
    assert len(jobs) == len(boards), "a board was dropped"
    assert stats.raw_count == len(boards)


def test_one_dead_board_does_not_lose_the_others(monkeypatch):
    """A single flaky aggregator must not empty the whole source."""
    from sources.adapters.aggregators_adapter import AggregatorsAdapter

    boards = _fake_boards(failing={"WorkingNomads", "NoDesk"})
    monkeypatch.setattr(AggregatorsAdapter, "BOARDS", boards)

    jobs, stats = AggregatorsAdapter().fetch_raw()
    urls = sorted(j.url for j in jobs)
    assert urls == [
        "https://x.test/Himalayas",
        "https://x.test/Jobspresso",
        "https://x.test/RemoteOK",
        "https://x.test/Remotive",
        "https://x.test/WeWorkRemotely",
    ]
    assert stats.raw_count == 5


def test_raw_count_matches_the_records_returned(monkeypatch):
    """stats.raw_count is summed after the gather, so it cannot drift."""
    from sources.adapters.aggregators_adapter import AggregatorsAdapter

    monkeypatch.setattr(AggregatorsAdapter, "BOARDS", _fake_boards())
    jobs, stats = AggregatorsAdapter().fetch_raw()
    assert stats.raw_count == len(jobs)
