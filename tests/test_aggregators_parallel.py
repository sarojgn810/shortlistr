"""The seven public boards are fetched together, not one after another.

Walked in series, the source cost the sum of its worst members: WorkingNomads
alone took 7.5s to return 1 job, and five of the seven spent 13.5s between them
for 4 jobs, while RemoteOK and Remotive delivered 134 in 2.5s. They are seven
different hosts, so overlapping them adds no load on any one of them.
"""

from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "automation"))


def _fake_boards(delay: float, tracker: dict, *, failing: set[str] | None = None):
    failing = failing or set()

    def make(label: str):
        def fn():
            tracker["in_flight"] += 1
            tracker["peak"] = max(tracker["peak"], tracker["in_flight"])
            try:
                time.sleep(delay)
                if label in failing:
                    raise RuntimeError(f"{label} is down")
                return [_Rec(f"https://x.test/{label}")]
            finally:
                tracker["in_flight"] -= 1

        return fn

    return [(lbl, make(lbl)) for lbl in
            ("Himalayas", "Remotive", "RemoteOK", "WeWorkRemotely",
             "WorkingNomads", "NoDesk", "Jobspresso")]


class _Rec:
    def __init__(self, url):
        self.url = url


def test_boards_are_fetched_concurrently(monkeypatch):
    from sources.adapters.aggregators_adapter import AggregatorsAdapter

    tracker = {"in_flight": 0, "peak": 0}
    delay = 0.25
    boards = _fake_boards(delay, tracker)
    monkeypatch.setattr(AggregatorsAdapter, "BOARDS", boards)

    t0 = time.monotonic()
    jobs, stats = AggregatorsAdapter().fetch_raw()
    elapsed = time.monotonic() - t0

    assert len(jobs) == len(boards), "a board was dropped"
    assert stats.raw_count == len(boards)
    assert tracker["peak"] > 1, "boards were fetched one at a time"
    # Sequential would be 7 * 0.25 = 1.75s.
    assert elapsed < len(boards) * delay * 0.6, f"looks sequential: {elapsed:.2f}s"


def test_one_dead_board_does_not_lose_the_others(monkeypatch):
    """A single flaky aggregator must not empty the whole source."""
    from sources.adapters.aggregators_adapter import AggregatorsAdapter

    tracker = {"in_flight": 0, "peak": 0}
    boards = _fake_boards(0.0, tracker, failing={"WorkingNomads", "NoDesk"})
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

    tracker = {"in_flight": 0, "peak": 0}
    monkeypatch.setattr(AggregatorsAdapter, "BOARDS", _fake_boards(0.0, tracker))
    jobs, stats = AggregatorsAdapter().fetch_raw()
    assert stats.raw_count == len(jobs)
