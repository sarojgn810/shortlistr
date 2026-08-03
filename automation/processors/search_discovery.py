"""
Level 3 discovery — run portals.yml search_queries via Google CSE, SerpAPI, or DuckDuckGo.

Finds Greenhouse/Lever/Ashby job URLs across the web without maintaining a company list.
"""

from __future__ import annotations

import logging
import os
import re
import time
from html import unescape
from typing import Callable
from urllib.parse import parse_qs, urlparse

import requests
import yaml

from paths import PORTALS_PATH
from scrapers.ats_url_resolver import is_ats_job_url, parse_ats_url, resolve_job_url
from tracker_tools.liveness import classify_liveness

logger = logging.getLogger(__name__)

FETCH_TIMEOUT = 8
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; shortlistr/1.0; search-discovery)",
}

# URLs worth keeping from search results
_ATS_URL = re.compile(
    r"https?://(?:"
    r"(?:boards-api|boards|job-boards)(?:\.eu)?\.greenhouse\.io/[^/\s]+/jobs/\d+|"
    r"jobs\.lever\.co/[^/\s]+/[a-f0-9-]{36}|"
    r"jobs\.ashbyhq\.com/[^/\s]+/[a-f0-9-]+"
    r")",
    re.I,
)

_TITLE_FROM_RESULT = re.compile(r"^(.+?)(?:\s+[@|–-]\s+|\s+\|)", re.I)


def _env(key: str, fallback: str = "") -> str:
    """Env var or secrets_store (Connections UI writes here)."""
    v = os.environ.get(key, "").strip()
    if v:
        return v
    try:
        from secrets_store import get_secret, has_secret

        if has_secret(key):
            return (get_secret(key) or "").strip() or fallback
    except Exception:
        pass
    return fallback


def search_backend_available() -> str | None:
    """Return backend name if credentials exist, else None.

    Prefer Google CSE when configured (free daily quota). DuckDuckGo is always
    usable as a last resort without credentials — callers that need “any
    backend” should fall through to it explicitly.
    """
    if _env("SERPAPI_KEY"):
        return "serpapi"
    if _env("GOOGLE_CSE_API_KEY") and _env("GOOGLE_CSE_CX"):
        return "google_cse"
    return "duckduckgo"


def extract_ats_urls(text: str) -> list[str]:
    """Pull ATS job URLs from arbitrary text (search snippets, HTML, etc.)."""
    found: list[str] = []
    seen: set[str] = set()
    for m in _ATS_URL.finditer(text or ""):
        url = m.group(0).rstrip(").,;\"'")
        if url not in seen:
            seen.add(url)
            found.append(url)
    return found


def parse_result_title(raw_title: str, url: str) -> str:
    """Best-effort title from a search result headline."""
    title = unescape((raw_title or "").strip())
    m = _TITLE_FROM_RESULT.match(title)
    if m:
        return m.group(1).strip()
    parsed = parse_ats_url(url)
    if parsed:
        job = resolve_job_url(url)
        if job:
            return job.get("title", title)
    return title or "Unknown role"


def _run_google_cse(query: str, num: int = 10) -> list[dict]:
    key = _env("GOOGLE_CSE_API_KEY")
    cx = _env("GOOGLE_CSE_CX")
    resp = requests.get(
        "https://www.googleapis.com/customsearch/v1",
        params={"key": key, "cx": cx, "q": query, "num": min(num, 10)},
        timeout=FETCH_TIMEOUT,
    )
    if resp.status_code >= 400:
        raise RuntimeError(_explain_cse_error(resp))
    return [
        {"title": i.get("title", ""), "url": i.get("link", ""), "snippet": i.get("snippet", "")}
        for i in resp.json().get("items", [])
    ]


def _explain_cse_error(resp) -> str:
    """Turn Google's HTTP status into the thing the user has to go and do.

    A bare "403 Forbidden" for a key that is correctly formatted and correctly
    pasted is not actionable, and the reason is only in the response body:
    creating an API key does not enable an API on the project it belongs to,
    which is the step people miss.
    """
    reason = ""
    try:
        err = (resp.json() or {}).get("error") or {}
        detail = str(err.get("message") or "").strip()
        for d in err.get("details") or []:
            if isinstance(d, dict) and d.get("reason"):
                reason = str(d["reason"])
                break
    except Exception:
        detail = ""

    if reason == "API_KEY_SERVICE_BLOCKED":
        return (
            "This API key is restricted and Custom Search is not on its allowed "
            "list. Open console.cloud.google.com/apis/credentials, click the "
            "key, and under “API restrictions” either choose “Don't restrict "
            "key” or add “Custom Search API” to the selected APIs. A new key "
            "created from the API's own page is often restricted to that API "
            "only, which is why a fresh key can fail differently from the one "
            "it replaced."
        )

    if resp.status_code == 403 and "does not have the access" in detail.lower():
        # Google returns this same sentence for two different causes, and the
        # response body does not distinguish them. Enabling the API is the one
        # people try first; when the dashboard then shows traffic but every
        # call still 403s, it is the other one — the key is restricted, or it
        # belongs to a different project than the one the API was enabled on.
        return (
            "Google Custom Search is refusing this key. Two things cause this "
            "exact error, so check both:\n"
            "1. The Custom Search JSON API is not enabled on the project the "
            "key belongs to — console.cloud.google.com/apis/library/"
            "customsearch.googleapis.com, and make sure the project selector "
            "matches the project the key was created in.\n"
            "2. The key is restricted and Custom Search is not on its allowed "
            "list — console.cloud.google.com/apis/credentials, click the key, "
            "and under “API restrictions” either choose “Don't restrict key” "
            "or add “Custom Search API”.\n"
            "If the API dashboard shows requests arriving but all failing, it "
            "is the second one."
        )
    if resp.status_code == 403:
        return (
            "Google Custom Search refused this key (403). If the key has "
            "application restrictions — HTTP referrer or IP — remove them: "
            f"Shortlistr calls the API from your machine, not a browser. {detail}"
        )
    if resp.status_code == 429:
        return (
            "Google Custom Search daily quota reached (100 queries/day on the "
            "free tier). It resets at midnight Pacific."
        )
    if resp.status_code == 400 and "api key not valid" in detail.lower():
        return (
            "Google rejected the API key itself. Check you copied the API key "
            "(starts with AIza) and not the OAuth client ID or the search "
            "engine ID."
        )
    return f"Google Custom Search error {resp.status_code}: {detail or resp.text[:160]}"


def _run_serpapi(query: str, num: int = 10) -> list[dict]:
    key = _env("SERPAPI_KEY")
    resp = requests.get(
        "https://serpapi.com/search",
        params={"api_key": key, "q": query, "num": min(num, 10), "engine": "google"},
        timeout=FETCH_TIMEOUT,
    )
    resp.raise_for_status()
    return [
        {
            "title": r.get("title", ""),
            "url": r.get("link", ""),
            "snippet": r.get("snippet", ""),
        }
        for r in resp.json().get("organic_results", [])
    ]


def _run_duckduckgo(query: str, num: int = 10) -> list[dict]:
    """Free fallback — HTML scrape; brittle but needs no API key."""
    resp = requests.post(
        "https://html.duckduckgo.com/html/",
        data={"q": query, "b": ""},
        headers={**HEADERS, "Content-Type": "application/x-www-form-urlencoded"},
        timeout=FETCH_TIMEOUT,
    )
    if resp.status_code == 202 or (
        "anomaly" in resp.text.lower() and 'class="result__a"' not in resp.text
    ):
        raise RuntimeError(
            f"DuckDuckGo challenged automated search (HTTP {resp.status_code})"
        )
    resp.raise_for_status()
    html = resp.text
    results: list[dict] = []
    for block in re.findall(
        r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        html,
        re.I | re.S,
    ):
        href, raw_title = block[0], re.sub(r"<[^>]+>", "", block[1])
        # DDG redirect: //duckduckgo.com/l/?uddg=...
        if "uddg=" in href:
            qs = parse_qs(urlparse(href).query)
            href = unescape(qs.get("uddg", [href])[0])
        results.append({"title": unescape(raw_title.strip()), "url": href, "snippet": ""})
        if len(results) >= num:
            break
    return results


def run_search_query(query: str, backend: str | None = None, num: int = 10) -> list[dict]:
    backend = backend or search_backend_available() or "duckduckgo"
    if backend == "serpapi":
        return _run_serpapi(query, num)
    if backend == "google_cse":
        return _run_google_cse(query, num)
    return _run_duckduckgo(query, num)


def check_url_liveness_http(url: str) -> dict[str, str]:
    """Lightweight liveness check without Playwright."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=FETCH_TIMEOUT, allow_redirects=True)
        body = resp.text[:8000]
        # Strip tags for classification
        text = re.sub(r"<script[^>]*>.*?</script>", " ", body, flags=re.I | re.S)
        text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.I | re.S)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", unescape(text)).strip()
        apply_hits = [m.group(0) for m in re.finditer(r"\bapply\b", text, re.I)]
        return classify_liveness(
            status=resp.status_code,
            final_url=resp.url,
            body_text=text,
            apply_controls=apply_hits[:5],
        )
    except Exception as e:
        return {"result": "expired", "reason": f"fetch error: {e}"}


def _auto_location_queries() -> list[dict]:
    """Generate search queries from profile target_titles × preferred_locations.

    This ensures users who set a preferred location actually get jobs from
    that city, even without manually writing portals.yml search_queries."""
    from config import search_locations, search_titles

    locations = search_locations(3)
    if not locations:
        return []

    titles = search_titles(4)
    if not titles:
        return []

    queries: list[dict] = []
    for loc in locations:
        for title in titles[:3]:
            queries.append({
                "query": f"{title} {loc} jobs apply",
                "name": f"auto:{title[:20]}+{loc}",
            })
    return queries


def load_search_queries(portals_path: str | None = None) -> list[dict]:
    path = portals_path or PORTALS_PATH
    if not os.path.exists(path):
        return _auto_location_queries()
    config = yaml.safe_load(open(path, encoding="utf-8")) or {}
    manual = [
        q for q in (config.get("search_queries") or [])
        if isinstance(q, dict) and q.get("enabled", True) is not False and q.get("query")
    ]
    from portals_config import get_websearch_company_queries

    company_queries, _ = get_websearch_company_queries(path, limit=8)
    return manual + company_queries + _auto_location_queries()


def discover_from_search(
    *,
    title_filter: Callable[[str], bool] | None = None,
    check_liveness: bool = True,
    backend: str | None = None,
    max_per_query: int = 10,
    portals_path: str | None = None,
) -> tuple[list[dict], dict]:
    """
    Run all enabled search_queries; return (offers, stats).

    Each offer: {title, url, company, location, source}
    """
    from portals_config import get_websearch_company_queries

    path = portals_path or PORTALS_PATH
    queries = load_search_queries(portals_path)
    _, websearch_stats = get_websearch_company_queries(path, limit=8)
    stats = {
        "queries_run": 0,
        "results_raw": 0,
        "ats_urls": 0,
        "resolved": 0,
        "liveness_expired": 0,
        "title_filtered": 0,
        "backend": backend or search_backend_available() or "duckduckgo",
        "error": "",
        "websearch_companies": websearch_stats.get("companies", 0),
        "websearch_skipped_no_query": websearch_stats.get("skipped_no_query", 0),
        "websearch_capped": websearch_stats.get("capped", 0),
    }
    if not queries:
        return [], stats

    offers: list[dict] = []
    seen_urls: set[str] = set()
    max_search_seconds = 30
    t_search_start = time.monotonic()
    consecutive_failures = 0

    for q in queries:
        if time.monotonic() - t_search_start > max_search_seconds:
            logger.warning("Search time cap reached (%ds) — skipping remaining queries", max_search_seconds)
            break
        if consecutive_failures >= 2:
            logger.warning("Search backend appears unreachable (%d consecutive failures) — skipping remaining queries", consecutive_failures)
            break

        name = q.get("name", q.get("query", "")[:40])
        query = q["query"]
        stats["queries_run"] += 1
        try:
            results = run_search_query(query, backend=backend, num=max_per_query)
            consecutive_failures = 0
        except Exception as e:
            logger.warning(f"Search query '{name}' failed: {e}")
            stats["error"] = str(e)
            consecutive_failures += 1
            continue

        stats["results_raw"] += len(results)
        for r in results:
            blob = " ".join([r.get("url", ""), r.get("title", ""), r.get("snippet", "")])
            for url in extract_ats_urls(blob):
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                stats["ats_urls"] += 1

                if check_liveness:
                    live = check_url_liveness_http(url)
                    if live.get("result") == "expired":
                        stats["liveness_expired"] += 1
                        continue

                job = resolve_job_url(url)
                if job:
                    stats["resolved"] += 1
                    title = job.get("title", "")
                    company = job.get("company", "")
                else:
                    title = parse_result_title(r.get("title", ""), url)
                    parsed = parse_ats_url(url)
                    company = (parsed.slug if parsed else "").replace("-", " ").title()

                if title_filter and not title_filter(title):
                    stats["title_filtered"] += 1
                    continue

                offers.append({
                    "title": title,
                    "url": job.get("url", url) if job else url,
                    "company": company or "Unknown",
                    "location": job.get("location", "") if job else "",
                    "source": "search-discovery",
                })

    return offers, stats
