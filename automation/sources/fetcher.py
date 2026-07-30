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


def cached_get_json(
    url: str,
    *,
    cache_key: str | None = None,
    ttl: int = DEFAULT_TTL,
    timeout: int = 12,
    headers: dict | None = None,
    retries: int = MAX_RETRIES,
) -> dict | list | None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    key = cache_key or url
    path = _cache_path(key)
    if os.path.exists(path):
        age = time.time() - os.path.getmtime(path)
        if age < ttl:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            resp = requests.get(url, timeout=timeout, headers=headers or {})
            if resp.status_code != 200:
                if resp.status_code >= 500 and attempt < retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                return None
            data = resp.json()
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f)
            return data
        except Exception as e:
            last_err = e
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    if last_err:
        return None
    return None


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
