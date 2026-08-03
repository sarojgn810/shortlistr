"""Reddit is where the questions are, and only the official API may read it.

robots.txt on reddit.com disallows crawling, so the page-fetching path skips it
along with Glassdoor and Blind. That left the best source unreachable. Reddit's
official API is free and permitted and returns the same threads as JSON, so it
is used instead — and it is entirely optional: with no app credentials this is a
no-op and the rest of the research still runs.
"""

from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))


THREAD = {
    "data": {
        "title": "Acme Corp SRE interview writeup",
        "selftext": (
            "Round 1: How would you design a multi-region metrics pipeline? "
            "Round 2: Describe a time you cut alert noise on a paging service? "
            "They also asked: What is your approach to writing a postmortem?"
        ),
    }
}


def _fake_reddit(monkeypatch, children, *, token="tok"):
    from prep import research

    research._REDDIT_TOKEN.update({"value": "", "expires": 0.0})
    monkeypatch.setattr(research, "_reddit_token", lambda: token)

    class Resp:
        status_code = 200
        @staticmethod
        def json():
            return {"data": {"children": children}}

    monkeypatch.setattr(research.requests, "get", lambda *a, **k: Resp())
    return research


# ── it reads what a scraper may not ──────────────────────────────────────────

def test_questions_come_back_from_a_thread(monkeypatch):
    research = _fake_reddit(monkeypatch, [THREAD])
    qs, read = research.reddit_interview_questions("Acme Corp", "Site Reliability Engineer")

    assert read == 1
    assert len(qs) >= 2, qs
    assert any("multi-region metrics pipeline" in q.lower() for q in qs)


def test_a_thread_that_never_names_the_company_is_ignored(monkeypatch):
    """Search is fuzzy. A post about a different employer is not evidence."""
    other = {"data": {"title": "Globex interview",
                      "selftext": "They asked: How do you scale Postgres writes?"}}
    research = _fake_reddit(monkeypatch, [other])
    qs, read = research.reddit_interview_questions("Acme Corp", "SRE")
    assert qs == [] and read == 0


# ── it is optional ───────────────────────────────────────────────────────────

def test_no_credentials_means_no_calls_and_no_error(monkeypatch):
    from prep import research

    monkeypatch.setattr(research, "_reddit_creds", lambda: ("", ""))
    research._REDDIT_TOKEN.update({"value": "", "expires": 0.0})

    called = []
    monkeypatch.setattr(research.requests, "post", lambda *a, **k: called.append(1))
    monkeypatch.setattr(research.requests, "get", lambda *a, **k: called.append(1))

    assert research.reddit_configured() is False
    assert research.reddit_interview_questions("Acme", "SRE") == ([], 0)
    assert called == [], "must not touch the network without credentials"


def test_an_auth_failure_degrades_quietly(monkeypatch):
    from prep import research

    research._REDDIT_TOKEN.update({"value": "", "expires": 0.0})
    monkeypatch.setattr(research, "_reddit_creds", lambda: ("id", "secret"))

    class Denied:
        status_code = 401
        @staticmethod
        def json():
            return {}

    monkeypatch.setattr(research.requests, "post", lambda *a, **k: Denied())
    assert research._reddit_token() == ""
    assert research.reddit_interview_questions("Acme", "SRE") == ([], 0)


def test_the_token_is_cached(monkeypatch):
    from prep import research

    research._REDDIT_TOKEN.update({"value": "", "expires": 0.0})
    monkeypatch.setattr(research, "_reddit_creds", lambda: ("id", "secret"))

    calls = []

    class Ok:
        status_code = 200
        @staticmethod
        def json():
            calls.append(1)
            return {"access_token": "abc", "expires_in": 3600}

    monkeypatch.setattr(research.requests, "post", lambda *a, **k: Ok())
    assert research._reddit_token() == "abc"
    assert research._reddit_token() == "abc"
    assert len(calls) == 1, "token should be fetched once, not per query"


# ── the wasted query is gone ─────────────────────────────────────────────────

def test_search_no_longer_targets_hosts_it_refuses_to_read():
    """Querying "Glassdoor OR Blind" spent a request on results we then skip."""
    import inspect

    from prep import research

    src = inspect.getsource(research.research_interview)
    block = src[src.index("queries = ["): src.index("all_hits")]
    # Only the query literals matter — the comment above them explains *why*
    # those hosts are not targeted, so it naturally mentions them.
    queries = "\n".join(
        ln for ln in block.splitlines() if not ln.lstrip().startswith("#"))
    assert "Glassdoor" not in queries and "Blind" not in queries
    assert "interview experience" in queries


# ── it is offered in the product, not just the code ──────────────────────────

def test_reddit_is_offered_in_onboarding_and_connections():
    for rel in ("dashboard/src/components/onboarding/ConnectStep.tsx",
                "dashboard/app/connections/page.tsx"):
        src = open(os.path.join(ROOT, rel), encoding="utf-8").read()
        assert "reddit_client_id" in src, f"{rel} does not collect the Reddit app id"
        assert "reddit_client_secret" in src
        assert "reddit/prefs/apps" in src or "prefs/apps" in src, (
            f"{rel} should link to where the credentials come from"
        )


def test_the_backend_accepts_what_the_ui_sends():
    import inspect

    import connections_store

    src = inspect.getsource(connections_store)
    assert 'body.get("reddit_client_id")' in src
    assert 'body.get("reddit_client_secret")' in src
    assert '"reddit": {' in src, "status payload must report readiness to the UI"


def test_the_request_model_accepts_the_reddit_fields():
    """Pydantic drops unknown keys silently.

    The store and the UI were both correct, but ConnectionsBody had no Reddit
    fields — so PUT /setup/connections returned 200 and persisted nothing. The
    save looked like it worked and the credential never arrived.
    """
    from api.main import ConnectionsBody

    fields = set(ConnectionsBody.model_fields)
    assert {"reddit_client_id", "reddit_client_secret"} <= fields

    body = ConnectionsBody(reddit_client_id="abc", reddit_client_secret="xyz")
    dumped = body.model_dump(exclude_unset=True)
    assert dumped == {"reddit_client_id": "abc", "reddit_client_secret": "xyz"}
