"""HTTP fetch with disk cache and async parallel helper."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from typing import Any

import requests

from config import DATA_DIR

CACHE_DIR = os.path.join(DATA_DIR, "cache")
DEFAULT_TTL = 7200  # 2 hours
MAX_RETRIES = 3


def _cache_path(key: str) -> str:
    safe = hashlib.sha256(key.encode()).hexdigest()[:32]
    return os.path.join(CACHE_DIR, f"{safe}.json")


def _resolve_ttl(ttl: int | None) -> int:
    """Read DEFAULT_TTL at call time, not at import.

    `jobs/ingest.py` lowers the window by assigning `fetcher.DEFAULT_TTL = 3300`
    so alternate 2h cron ticks cannot serve the same cached snapshot. That only
    works if the value is looked up when the request happens — as a default
    argument it was bound once at import, so the override silently did nothing
    and every ingest kept the 7200s window it was trying to avoid.
    """
    return DEFAULT_TTL if ttl is None else ttl


def _read_cache(path: str, ttl: int) -> Any | None:
    if os.path.exists(path) and time.time() - os.path.getmtime(path) < ttl:
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return None  # a truncated cache file must not break the fetch
    return None


def _write_cache(path: str, data: Any) -> None:
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except OSError:
        pass  # an unwritable cache costs speed, never correctness


def _fetch_with_retries(send, path: str, retries: int) -> dict | list | None:
    for attempt in range(retries):
        try:
            resp = send()
            if resp.status_code != 200:
                if resp.status_code >= 500 and attempt < retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                return None
            data = resp.json()
            _write_cache(path, data)
            return data
        except Exception:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    return None


def cached_get_json(
    url: str,
    *,
    cache_key: str | None = None,
    ttl: int | None = None,
    timeout: int = 12,
    headers: dict | None = None,
    retries: int = MAX_RETRIES,
) -> dict | list | None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = _cache_path(cache_key or url)
    hit = _read_cache(path, _resolve_ttl(ttl))
    if hit is not None:
        return hit
    return _fetch_with_retries(
        lambda: requests.get(url, timeout=timeout, headers=headers or {}),
        path,
        retries,
    )


def text_cache_key(url: str, params: dict | None = None) -> str:
    return f"{url}|{json.dumps(params or {}, sort_keys=True)}"


def read_cached_text(key: str, *, ttl: int | None = None) -> str | None:
    """Read a cached HTML body, or None.

    Split from the write half because the one caller — LinkedIn guest search —
    has to keep its own request semantics: a 429 with Retry-After, and a raise on
    any other non-200. Handing that to a generic fetch helper would either fight
    the backoff or swallow the block.
    """
    os.makedirs(CACHE_DIR, exist_ok=True)
    hit = _read_cache(_cache_path(key), _resolve_ttl(ttl))
    return hit if isinstance(hit, str) else None


def write_cached_text(key: str, text: str) -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    _write_cache(_cache_path(key), text)


def cached_post_json(
    url: str,
    payload: dict,
    *,
    cache_key: str | None = None,
    ttl: int | None = None,
    timeout: int = 12,
    headers: dict | None = None,
    retries: int = MAX_RETRIES,
) -> dict | list | None:
    """Same disk cache, for APIs that only answer POST (Workday's CXS endpoint).

    The body is part of the identity of the request. Workday pages a board by
    posting a different `offset` to the *same* URL, so keying on the URL alone
    would serve page 1's postings for pages 2 and 3 — the board would look like
    it had 20 jobs repeated three times. The default key is url + the payload,
    canonicalised with sorted keys so dict ordering cannot split the cache.
    """
    os.makedirs(CACHE_DIR, exist_ok=True)
    key = cache_key or f"{url}|{json.dumps(payload, sort_keys=True)}"
    path = _cache_path(key)
    hit = _read_cache(path, _resolve_ttl(ttl))
    if hit is not None:
        return hit
    return _fetch_with_retries(
        lambda: requests.post(url, json=payload, timeout=timeout, headers=headers or {}),
        path,
        retries,
    )


async def fetch_urls_parallel(
    urls: list[str],
    *,
    max_concurrent: int = 10,
    timeout: int = 12,
) -> list[tuple[str, dict | list | None]]:
    """Async parallel GET for multiple URLs (uses httpx if available, else thread pool)."""
    try:
        import httpx
    except ImportError:
        results = []
        for url in urls:
            results.append((url, cached_get_json(url, timeout=timeout)))
        return results

    sem = asyncio.Semaphore(max_concurrent)

    async def one(client: httpx.AsyncClient, url: str):
        async with sem:
            try:
                r = await client.get(url, timeout=timeout)
                if r.status_code == 200:
                    return url, r.json()
            except Exception:
                pass
            return url, None

    async def run():
        async with httpx.AsyncClient() as client:
            return await asyncio.gather(*[one(client, u) for u in urls])

    return await run()
