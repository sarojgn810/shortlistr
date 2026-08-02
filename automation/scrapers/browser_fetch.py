"""Fetch a page as HTML: requests first, Playwright only for empty SPA shells."""

from __future__ import annotations

import hashlib
import logging
import os
import re
import time
from dataclasses import dataclass

import requests

from config import DATA_DIR

logger = logging.getLogger(__name__)

CACHE_DIR = os.path.join(DATA_DIR, "cache", "pages")
DEFAULT_TTL = 7200
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

_SPA_EMPTY_MARKERS = (
    "enable javascript",
    "javascript is required",
    "you need to enable javascript",
    "noscript",
)
_BLOCKED_HOST_FRAGMENTS = (
    "naukri.com",
    "linkedin.com/checkpoint",
    "captcha",
)


@dataclass
class PageFetch:
    url: str
    html: str = ""
    final_url: str = ""
    status: int = 0
    via: str = ""  # requests | playwright | cache
    error: str = ""


def _cache_path(url: str) -> str:
    digest = hashlib.sha256(url.encode()).hexdigest()[:32]
    return os.path.join(CACHE_DIR, f"{digest}.html")


def _looks_like_empty_spa(html: str) -> bool:
    if not html or len(html) < 800:
        return True
    lower = html.lower()
    if any(m in lower for m in _SPA_EMPTY_MARKERS):
        # Only treat as empty if body text is also thin.
        text = re.sub(r"<script[\s\S]*?</script>", "", html, flags=re.I)
        text = re.sub(r"<style[\s\S]*?</style>", "", text, flags=re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) < 400:
            return True
    # Next/Nuxt root with almost no rendered content.
    if re.search(r'id=["\']__next["\'][^>]*>\s*</div>', html, re.I) and len(html) < 4000:
        return True
    if "__NEXT_DATA__" in html:
        return False
    return False


def _blocked(url: str) -> str:
    lower = (url or "").lower()
    for frag in _BLOCKED_HOST_FRAGMENTS:
        if frag in lower:
            return f"skipped blocked host ({frag})"
    return ""


def _from_cache(url: str, ttl: int) -> PageFetch | None:
    path = _cache_path(url)
    if not os.path.isfile(path):
        return None
    age = time.time() - os.path.getmtime(path)
    if age > ttl:
        return None
    try:
        html = open(path, encoding="utf-8").read()
    except OSError:
        return None
    return PageFetch(url=url, html=html, final_url=url, status=200, via="cache")


def _store_cache(url: str, html: str) -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    try:
        open(_cache_path(url), "w", encoding="utf-8").write(html)
    except OSError:
        pass


def _fetch_requests(url: str, timeout: int) -> PageFetch:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        return PageFetch(
            url=url,
            html=resp.text or "",
            final_url=str(resp.url or url),
            status=int(resp.status_code),
            via="requests",
            error="" if resp.status_code == 200 else f"HTTP {resp.status_code}",
        )
    except Exception as exc:
        return PageFetch(url=url, error=str(exc), via="requests")


def _fetch_playwright(url: str, timeout_ms: int = 15000) -> PageFetch:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return PageFetch(
            url=url,
            error="Playwright not installed — open Connections → Install Playwright",
            via="playwright",
        )
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                resp = page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                html = page.content()
                status = int(resp.status) if resp else 0
                final = page.url
            finally:
                browser.close()
        return PageFetch(
            url=url,
            html=html or "",
            final_url=final,
            status=status,
            via="playwright",
            error="" if status and status < 400 else f"HTTP {status}",
        )
    except Exception as exc:
        return PageFetch(url=url, error=str(exc), via="playwright")


def fetch_page(
    url: str,
    *,
    timeout: int = 15,
    ttl: int = DEFAULT_TTL,
    allow_browser: bool = True,
    allow_page_reader: bool | None = None,
) -> PageFetch:
    """Fetch HTML for a job/careers URL. Never submits forms.

    Order: cache → requests → optional page reader (when enabled) → Playwright.
    """
    block = _blocked(url)
    if block:
        return PageFetch(url=url, error=block)

    cached = _from_cache(url, ttl)
    if cached:
        return cached

    page = _fetch_requests(url, timeout=timeout)
    if page.status in (403, 429) or (page.error and not page.html):
        reader = _try_page_reader(url, timeout=timeout, allow=allow_page_reader)
        if reader:
            return reader
        return page

    if page.status == 200 and page.html and not _looks_like_empty_spa(page.html):
        _store_cache(url, page.html)
        return page

    # Thin SPA / empty shell — prefer page reader (fast, no browser) when opted in.
    reader = _try_page_reader(url, timeout=timeout, allow=allow_page_reader)
    if reader:
        return reader

    if not allow_browser:
        if not page.error and _looks_like_empty_spa(page.html):
            page.error = "empty SPA shell (browser fetch disabled)"
        return page

    browser = _fetch_playwright(url)
    if browser.html and not browser.error:
        _store_cache(url, browser.html)
        return browser
    # Prefer browser error if requests only got an empty shell.
    if _looks_like_empty_spa(page.html) and browser.error:
        return browser
    return page if page.html else browser


def _try_page_reader(
    url: str, *, timeout: int, allow: bool | None
) -> PageFetch | None:
    use = allow
    if use is None:
        try:
            from scrapers.page_reader import is_enabled

            use = is_enabled()
        except Exception:
            use = False
    if not use:
        return None
    try:
        from scrapers.page_reader import fetch_via_reader, markdown_as_html

        text, err = fetch_via_reader(url, timeout=max(timeout, 20))
        if err or not text:
            logger.debug("Page reader skip for %s: %s", url[:80], err)
            return None
        html = markdown_as_html(text)
        _store_cache(url, html)
        return PageFetch(
            url=url,
            html=html,
            final_url=url,
            status=200,
            via="page_reader",
        )
    except Exception as exc:
        logger.debug("Page reader fetch failed: %s", exc)
        return None
