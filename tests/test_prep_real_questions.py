"""Interview questions must be real, or honestly labelled as not.

The guide used to fall back to a generic practice bank whenever research found
nothing — which was always, because DuckDuckGo now answers HTTP 202 to these
queries and no search key was configured. A candidate opening the guide saw
eight plausible questions under the company's name that nobody had ever been
asked there.

Two things changed. Questions are now read from the body of the result pages
rather than the ~160-character snippet, which is where reported questions
actually live. And when nothing is found the guide says so instead of padding.

Glassdoor and Blind are deliberately never fetched: both disallow it in
robots.txt and gate the content behind a login. An MIT licence is not
permission to break a site's terms.
"""

from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))


# ── robots.txt is obeyed ─────────────────────────────────────────────────────

def test_hosts_that_forbid_fetching_are_never_requested(monkeypatch):
    from prep import research

    requested = []
    monkeypatch.setattr(research, "_robots_allows", lambda url: True)
    monkeypatch.setattr(research, "_page_text",
                        lambda url: requested.append(url) or "")

    hits = [
        {"link": "https://www.glassdoor.com/Interview/acme-questions.htm"},
        {"link": "https://www.teamblind.com/post/acme-sre"},
        {"link": "https://www.linkedin.com/posts/someone_interview"},
    ]
    research.questions_from_pages(hits)
    assert requested == [], f"fetched a disallowed host: {requested}"


def test_an_unreadable_robots_txt_means_do_not_fetch(monkeypatch):
    """Absence of permission is not permission."""
    from prep import research

    research._ROBOTS_CACHE.clear()

    class Boom:
        def set_url(self, u): pass
        def read(self): raise OSError("no robots.txt")

    monkeypatch.setattr("urllib.robotparser.RobotFileParser", Boom)
    assert research._robots_allows("https://example.com/thread") is False


def test_robots_disallow_blocks_the_fetch(monkeypatch):
    from prep import research

    research._ROBOTS_CACHE.clear()

    class Deny:
        def set_url(self, u): pass
        def read(self): pass
        def can_fetch(self, ua, url): return False

    monkeypatch.setattr("urllib.robotparser.RobotFileParser", Deny)
    assert research._robots_allows("https://example.com/thread") is False


# ── questions come out of the page body ──────────────────────────────────────

PAGE = (
    "I interviewed at Acme last month for the SRE role. "
    "First round: How would you design a multi-region metrics pipeline? "
    "Then: Describe a time you reduced alert fatigue on a noisy service? "
    "Finally they asked: What is your approach to writing a postmortem? "
    "Good luck everyone."
)


def test_questions_are_read_from_the_page_not_the_snippet(monkeypatch):
    from prep import research

    monkeypatch.setattr(research, "_robots_allows", lambda url: True)
    monkeypatch.setattr(research, "_page_text", lambda url: PAGE)
    monkeypatch.setattr(research.time, "sleep", lambda s: None)

    qs, sources = research.questions_from_pages(
        [{"link": "https://www.reddit.com/r/sre/comments/abc/acme"}])

    assert len(qs) >= 2, qs
    assert any("multi-region metrics pipeline" in q.lower() for q in qs)
    assert sources == ["www.reddit.com"]


def test_fetching_is_capped(monkeypatch):
    """A prep run must not crawl. Approval waits on this."""
    from prep import research

    calls = []
    monkeypatch.setattr(research, "_robots_allows", lambda url: True)
    monkeypatch.setattr(research, "_page_text",
                        lambda url: calls.append(url) or PAGE)
    monkeypatch.setattr(research.time, "sleep", lambda s: None)

    hits = [{"link": f"https://example{i}.com/t"} for i in range(20)]
    research.questions_from_pages(hits, limit=200)
    assert len(calls) <= research._MAX_PAGES, f"fetched {len(calls)} pages"


def test_a_dead_page_does_not_break_the_run(monkeypatch):
    from prep import research

    monkeypatch.setattr(research, "_robots_allows", lambda url: True)
    monkeypatch.setattr(research, "_page_text", lambda url: "")
    monkeypatch.setattr(research.time, "sleep", lambda s: None)

    qs, sources = research.questions_from_pages([{"link": "https://example.com/t"}])
    assert qs == [] and sources == []


# ── the guide never pads ─────────────────────────────────────────────────────

def test_the_generic_practice_bank_is_not_used_in_the_guide():
    """It may still exist as a helper; it must not reach the rendered guide."""
    import inspect

    from processors import generate_prep

    src = inspect.getsource(generate_prep)
    body = src[src.index("## Interview Questions"):]
    body = body[: body.index("def ") if "def " in body else len(body)]
    assert "_fallback_practice_questions" not in body, (
        "the guide still falls back to a generic practice set"
    )


def test_the_guide_says_where_the_questions_came_from():
    import inspect

    from processors import generate_prep

    src = inspect.getsource(generate_prep)
    # Three distinct levels of evidence, and the guide must name which one.
    assert "Read from candidate reports on the public web" in src
    assert "From web search result summaries" in src
    assert "Written from this job description" in src
    assert "Generic practice set" not in src, (
        "a generic set must never be presented as a guide source"
    )


def test_empty_state_tells_the_user_how_to_get_real_questions():
    import inspect

    from processors import generate_prep

    src = inspect.getsource(generate_prep)
    assert "No interview reports were found" in src
    assert "Google Custom Search" in src, "must name the key that fixes it"


# ── search order ─────────────────────────────────────────────────────────────

def test_a_configured_api_is_tried_before_the_blocked_scraper():
    """DuckDuckGo answers HTTP 202 to these queries; trying it first only
    added latency before falling through to the backend that works."""
    import inspect

    from prep import research

    src = inspect.getsource(research.web_organic)
    cse_at = src.index("search_backend_available")
    ddg_at = src.index("_ddg_blocked")
    assert cse_at < ddg_at, "the configured API must be tried first"


def test_jd_derived_questions_are_not_labelled_as_practice():
    """They are written from this posting, so they must not read as a bank.

    The generic set had already been removed from the guide, but
    _llm_practice_questions still prefixed its own JD-derived questions with
    "PRACTICE ·", which looks identical to filler on the page.
    """
    import inspect

    from processors import generate_prep

    src = inspect.getsource(generate_prep._llm_practice_questions)
    assert "FROM THIS POSTING" in src
    assert "PRACTICE \u00b7" not in src and "PRACTICE ·" not in src
