"""Decoder bias vocabulary.

Every term here earned its place from a real transcript. Unprompted, Whisper
turned "evaluate" into "evolve rate" and "evil loot", "pipeline" into "eye
plane", and "Accenture DevOps" into "Essenture Dilops" — each of which routed to
the LLM instead of running the tool the user asked for.
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))


def test_covers_the_words_that_decide_routing():
    from voice import vocabulary

    words = vocabulary.hotwords(include_companies=False).lower()
    for term in ("shortlistr", "evaluate", "pipeline", "inbox", "tracker", "approve", "skip"):
        assert term in words, term


def test_includes_employers_from_the_users_own_pipeline(monkeypatch):
    from voice import vocabulary

    vocabulary.reset_cache()
    monkeypatch.setattr(vocabulary, "_recent_companies", lambda: ["Accenture", "Stripe"])

    words = vocabulary.hotwords()

    # Company names cannot be enumerated ahead of time, but the ones a user says
    # out loud are the ones already in their job list.
    assert "Accenture" in words
    assert "Stripe" in words


def test_companies_are_cached_rather_than_read_per_utterance(monkeypatch):
    from voice import vocabulary

    vocabulary.reset_cache()
    calls = []

    class FakeConn:
        def execute(self, *a):
            calls.append(1)
            return self

        def fetchall(self):
            return [("Stripe",)]

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    import store.db as db

    monkeypatch.setattr(db, "db", lambda: FakeConn())

    vocabulary.hotwords()
    vocabulary.hotwords()
    vocabulary.hotwords()

    # This runs on the latency-critical path — once per utterance would put a
    # database round trip in front of every spoken word.
    assert len(calls) == 1


def test_survives_an_unreadable_database(monkeypatch):
    from voice import vocabulary

    vocabulary.reset_cache()

    def boom():
        raise RuntimeError("database is locked")

    import store.db as db

    monkeypatch.setattr(db, "db", boom)

    # Slightly worse recognition beats transcription failing outright.
    words = vocabulary.hotwords()

    assert "Shortlistr" in words


def test_reset_clears_the_cache(monkeypatch):
    from voice import vocabulary

    vocabulary.reset_cache()
    monkeypatch.setattr(vocabulary, "_recent_companies", lambda: ["Acme"])
    assert "Acme" in vocabulary.hotwords()

    vocabulary.reset_cache()
    assert vocabulary._companies == []
