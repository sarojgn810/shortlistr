"""Disk cache for source fetches — POST support and the TTL override.

Workday's CXS endpoint only answers POST, and it pages a board by posting a
different offset to the *same* URL. Keying the cache on the URL alone would hand
page 1's postings back for pages 2 and 3, so a board would look like the same 20
jobs three times.
"""

from __future__ import annotations

import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))


@pytest.fixture
def cache_dir(monkeypatch, tmp_path):
    from sources import fetcher

    monkeypatch.setattr(fetcher, "CACHE_DIR", str(tmp_path))
    return tmp_path


class _Resp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload


# ── TTL is read at call time ─────────────────────────────────────────────────

def test_default_ttl_is_read_when_the_request_happens(monkeypatch):
    """jobs/ingest.py lowers DEFAULT_TTL to 3300 by assigning the module attr.

    As a default argument the value was bound once at import, so the override
    silently did nothing and ingest kept the very 7200s window it was avoiding.
    """
    from sources import fetcher

    monkeypatch.setattr(fetcher, "DEFAULT_TTL", 3300)
    assert fetcher._resolve_ttl(None) == 3300
    assert fetcher._resolve_ttl(60) == 60, "an explicit ttl still wins"


def test_a_lowered_ttl_makes_a_recent_entry_stale(cache_dir, monkeypatch):
    from sources import fetcher

    calls = []

    def fake_post(url, json=None, timeout=None, headers=None):
        calls.append(url)
        return _Resp({"n": len(calls)})

    monkeypatch.setattr(fetcher.requests, "post", fake_post)

    fetcher.cached_post_json("https://x.test/j", {"offset": 0})
    fetcher.cached_post_json("https://x.test/j", {"offset": 0})
    assert len(calls) == 1, "second call should have been served from cache"

    # Same request, but nothing may be considered fresh any more.
    monkeypatch.setattr(fetcher, "DEFAULT_TTL", 0)
    fetcher.cached_post_json("https://x.test/j", {"offset": 0})
    assert len(calls) == 2, "ttl override did not reach the request"


# ── POST cache keys ──────────────────────────────────────────────────────────

def test_pages_of_one_board_do_not_share_a_cache_entry(cache_dir, monkeypatch):
    """The bug this guards: same URL, different offset, one cache file."""
    from sources import fetcher

    def fake_post(url, json=None, timeout=None, headers=None):
        return _Resp({"jobPostings": [{"title": f"offset-{json['offset']}"}]})

    monkeypatch.setattr(fetcher.requests, "post", fake_post)

    seen = [
        fetcher.cached_post_json("https://x.test/j", {"offset": o, "limit": 20})[
            "jobPostings"
        ][0]["title"]
        for o in (0, 20, 40)
    ]
    assert seen == ["offset-0", "offset-20", "offset-40"]
    assert len(list(cache_dir.iterdir())) == 3, "pages collapsed into one entry"


def test_cache_key_is_stable_across_dict_ordering(cache_dir, monkeypatch):
    from sources import fetcher

    calls = []

    def fake_post(url, json=None, timeout=None, headers=None):
        calls.append(json)
        return _Resp({"ok": True})

    monkeypatch.setattr(fetcher.requests, "post", fake_post)

    fetcher.cached_post_json("https://x.test/j", {"limit": 20, "offset": 0})
    fetcher.cached_post_json("https://x.test/j", {"offset": 0, "limit": 20})
    assert len(calls) == 1, "key ordering split one request into two cache entries"


def test_a_second_call_is_served_from_disk(cache_dir, monkeypatch):
    from sources import fetcher

    calls = []

    def fake_post(url, json=None, timeout=None, headers=None):
        calls.append(url)
        return _Resp({"jobPostings": [{"title": "a"}]})

    monkeypatch.setattr(fetcher.requests, "post", fake_post)

    first = fetcher.cached_post_json("https://x.test/j", {"offset": 0})
    second = fetcher.cached_post_json("https://x.test/j", {"offset": 0})
    assert first == second
    assert len(calls) == 1


def test_a_failed_post_is_not_cached(cache_dir, monkeypatch):
    """Caching a 500 would hide a board for the whole TTL."""
    from sources import fetcher

    def fake_post(url, json=None, timeout=None, headers=None):
        return _Resp(None, status=404)

    monkeypatch.setattr(fetcher.requests, "post", fake_post)

    assert fetcher.cached_post_json("https://x.test/j", {"offset": 0}, retries=1) is None
    assert list(cache_dir.iterdir()) == []


def test_a_corrupt_cache_file_falls_back_to_the_network(cache_dir, monkeypatch):
    from sources import fetcher

    key = f"https://x.test/j|{json.dumps({'offset': 0}, sort_keys=True)}"
    path = fetcher._cache_path(key)
    os.makedirs(fetcher.CACHE_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("{ truncated")

    monkeypatch.setattr(
        fetcher.requests, "post",
        lambda url, json=None, timeout=None, headers=None: _Resp({"ok": True}),
    )
    assert fetcher.cached_post_json("https://x.test/j", {"offset": 0}) == {"ok": True}
