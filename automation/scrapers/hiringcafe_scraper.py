"""hiring.cafe — crawled through the sitemaps they publish for crawlers.

Their robots.txt explicitly allows `/job`, `/job/`, `/jobs`, `/jobs/` and
`/recently-posted-jobs`, and advertises five sitemaps. It disallows `/viewjob/`,
`/org/`, `/company/` and `/cdn-cgi/`, none of which are needed here. Their
`/api/search-jobs` endpoint answers 401 — it is private, so it is left alone
even though it would be the convenient thing to call.

Job pages are server-rendered and carry a JSON-LD `JobPosting` block, so the
title, company, location and description come from structured data the site
publishes for exactly this purpose, rather than from scraped markup that breaks
on the next redesign.

Dice was requested alongside this and is deliberately absent. Its robots.txt
disallows `/job`, `/jobsearch/`, `/jobs?q*`, `/jobs/?q*`, `/feed/` and `/rss/` —
every path a posting lives on, including the feeds. There is no permitted way
in, the same conclusion reached for Jobsora.
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime
from typing import Any

from models.job import JobRecord

logger = logging.getLogger(__name__)

BASE = "https://hiringcafe.com"
ROBOTS = f"{BASE}/robots.txt"
# Sitemap of currently-promoted postings — a few thousand, refreshed daily, and
# far smaller than walking the 441 shard chunks of the full posting sitemap.
PRIORITY_INDEX = f"{BASE}/priority-jobs-sitemap.xml"
# The full posting sitemap, sharded into 441 chunks. The priority sitemap alone
# is dominated by whatever the site is promoting that day — on the first run it
# was policing and nursing, and one posting in 2,200 matched an SRE profile — so
# the shards are sampled too rather than relying on the front page of the index.
POSTING_INDEX = f"{BASE}/job-posting-sitemap.xml"
MAX_CHUNKS = 12
# Their robots.txt sets no Crawl-delay. One second is a courtesy, not a rule.
CRAWL_DELAY = 1.0
MAX_JOBS = 60

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

_LOC_RE = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>", re.I)
_LD_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.I | re.S,
)


def _fetch(url: str, timeout: int = 25) -> str:
    import requests

    r = requests.get(url, headers=HEADERS, timeout=timeout)
    return r.text if r.status_code == 200 else ""


def _get(url: str, timeout: int = 25) -> str:
    """Fetch through the disk cache — sitemaps and postings both re-read often."""
    from sources.fetcher import read_cached_text, text_cache_key, write_cached_text

    key = text_cache_key(url)
    text = read_cached_text(key)
    if text is None:
        text = _fetch(url, timeout=timeout)
        if text:
            write_cached_text(key, text)
    return text or ""


def _sitemap_locs(xml: str) -> list[str]:
    return [m.group(1).strip() for m in _LOC_RE.finditer(xml or "")]


def _job_posting_from_html(html: str) -> dict[str, Any] | None:
    """The JSON-LD JobPosting block, if the page has one.

    A page can carry several LD blocks (breadcrumbs, organisation, website), and
    a block can be a @graph list rather than one object, so every candidate is
    examined instead of assuming the first is the posting.
    """
    for m in _LD_RE.finditer(html or ""):
        raw = (m.group(1) or "").strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            continue
        for node in _walk_ld(data):
            if str(node.get("@type") or "").lower() == "jobposting":
                return node
    return None


def _walk_ld(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict):
        out = [data]
        for key in ("@graph", "itemListElement"):
            if key in data:
                out.extend(_walk_ld(data[key]))
        return out
    if isinstance(data, list):
        out: list[dict[str, Any]] = []
        for item in data:
            out.extend(_walk_ld(item))
        return out
    return []


def _text(value: Any) -> str:
    if isinstance(value, str):
        return re.sub(r"<[^>]+>", " ", value)
    return ""


def _company(node: dict[str, Any]) -> str:
    org = node.get("hiringOrganization")
    if isinstance(org, dict):
        return str(org.get("name") or "").strip()
    if isinstance(org, str):
        return org.strip()
    return ""


def _location(node: dict[str, Any]) -> str:
    loc = node.get("jobLocation")
    if isinstance(loc, list):
        loc = loc[0] if loc else None
    if isinstance(loc, dict):
        addr = loc.get("address")
        if isinstance(addr, dict):
            parts = [addr.get("addressLocality"), addr.get("addressRegion"),
                     addr.get("addressCountry")]
            flat = [str(p).strip() for p in parts if isinstance(p, str) and p.strip()]
            if flat:
                return ", ".join(dict.fromkeys(flat))
    if str(node.get("jobLocationType") or "").upper() == "TELECOMMUTE":
        return "Remote"
    return ""


def _matches_profile(title: str, keywords: list[str]) -> bool:
    from pipeline.filter import _title_matches

    return bool(keywords) and _title_matches(title, keywords)


def fetch_jobs(keywords: list[str] | None = None, limit: int = MAX_JOBS) -> list[JobRecord]:
    """Postings from the priority sitemap whose slug looks like a target title.

    The slug is filtered before the page is fetched. The sitemap holds a couple
    of thousand postings across every trade there is — nursing, policing,
    driving — and fetching all of them to discard the ones that do not match
    would be both slow and rude.
    """
    if keywords is None:
        try:
            from config import SEARCH_KEYWORDS

            keywords = list(SEARCH_KEYWORDS or [])
        except Exception:
            keywords = []
    if not keywords:
        logger.info("hiring.cafe: no target titles configured; skipping")
        return []

    try:
        index = _get(PRIORITY_INDEX)
    except Exception as exc:
        logger.warning("hiring.cafe: sitemap index unreachable: %s", exc)
        return []

    chunks = _sitemap_locs(index)
    try:
        chunks += _sitemap_locs(_get(POSTING_INDEX))
    except Exception as exc:
        logger.debug("hiring.cafe: posting index unavailable: %s", exc)

    urls: list[str] = []
    for chunk in chunks[:MAX_CHUNKS]:
        try:
            urls.extend(_sitemap_locs(_get(chunk)))
        except Exception as exc:
            logger.debug("hiring.cafe: chunk %s failed: %s", chunk, exc)
        if len(urls) > 8000:
            break

    # The slug carries the role, so matching here avoids fetching a page per
    # posting only to throw it away.
    candidates = [u for u in urls if "/job/" in u and _slug_matches(u, keywords)]
    logger.info("hiring.cafe: %s postings in sitemap, %s match target titles",
                len(urls), len(candidates))

    records: list[JobRecord] = []
    for url in candidates[:limit]:
        try:
            node = _job_posting_from_html(_get(url))
        except Exception as exc:
            logger.debug("hiring.cafe: %s failed: %s", url, exc)
            continue
        finally:
            time.sleep(CRAWL_DELAY)
        if not node:
            continue
        title = str(node.get("title") or "").strip()
        if not title or not _matches_profile(title, keywords):
            continue
        records.append(
            JobRecord(
                url=url,
                source="hiringcafe",
                company=_company(node) or "Unknown",
                title=title,
                location=_location(node),
                jd_text=_text(node.get("description")).strip()[:20000],
            )
        )

    logger.info("hiring.cafe: %s jobs", len(records))
    return records


def _slug_matches(url: str, keywords: list[str]) -> bool:
    slug = url.rsplit("/job/", 1)[-1].replace("-", " ")
    from pipeline.filter import _title_matches

    return _title_matches(slug, keywords)


def _iso_today() -> str:
    return datetime.now().strftime("%Y-%m-%d")
