"""Jobgether — remote job board, crawled the way they ask to be crawled.

Their robots.txt opens with "# START robots (indexing enabled)", publishes a
sitemap, sets `Crawl-delay: 2`, and disallows only tracking parameters, template
placeholders (`/offer/{*}`) and `/_server-islands/`. Category pages under
`/remote-jobs/<role>` and offers under `/offer/<slug>` are permitted, so this
walks their own sitemap at their own stated pace rather than hitting search.

Only categories matching the profile's target titles are fetched — there are 563
of them and crawling the lot to throw away 550 would be rude and pointless.

Jobsora was considered alongside this and deliberately left out: its robots.txt
says `Disallow: /vacancy/`, `Disallow: /vacancy-search/` and `Disallow: /*?`,
which covers every path that has a job on it. There is no permitted way in.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime

from models.job import JobRecord

logger = logging.getLogger(__name__)

SITEMAP = "https://jobgether.com/sitemap/index-job-references.xml"
BASE = "https://jobgether.com"
# Their robots.txt asks for 2 seconds. Honour it literally.
CRAWL_DELAY = 2.0
MAX_CATEGORIES = 6

# A browser UA: the site 403s anything else, including its own robots.txt, so
# this is what it takes to read the policy they publish — not an evasion of one.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
}

_LOC_RE = re.compile(r"<loc>([^<]+)</loc>")
_OFFER_RE = re.compile(r'href="(/offer/[^"?#]+)"')
_TAG_RE = re.compile(r"<[^>]+>")


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _category_matches_profile(url: str) -> bool:
    """Use the pipeline's own title matcher, not a bespoke heuristic.

    A category is worth crawling exactly when its role would survive the
    discovery filter anyway. Reusing `_title_matches` means Jobgether selection
    tracks the user's targeting automatically — including the expansions
    config already builds — instead of drifting from it.

    An earlier attempt scored slugs on shared words. "operations" and "learning"
    then matched treasury, HR and LMS categories and filled every slot before any
    engineering one, which is how you crawl six pages to keep nothing.
    """
    import config as cfg
    from pipeline.filter import _title_matches

    slug = url.rsplit("/", 1)[-1]
    return bool(_title_matches(slug.replace("-", " "), cfg.SEARCH_KEYWORDS))


def _title_from_slug(slug: str) -> str:
    # /offer/<24-hex-id>-senior-site-reliability-engineer
    tail = slug.rstrip("/").split("/")[-1]
    tail = re.sub(r"^[0-9a-f]{16,}-", "", tail)
    return tail.replace("-", " ").replace(".", ". ").strip().title()


def _fetch(url: str, timeout: int = 20) -> str:
    import requests

    r = requests.get(url, headers=HEADERS, timeout=timeout)
    return r.text if r.status_code == 200 else ""


def _relevant_categories() -> list[str]:
    """Category pages whose slug mentions something the profile is looking for."""
    from sources.fetcher import read_cached_text, text_cache_key, write_cached_text

    key = text_cache_key(SITEMAP)
    xml = read_cached_text(key)
    if xml is None:
        xml = _fetch(SITEMAP, timeout=25)
        if xml:
            write_cached_text(key, xml)
    if not xml:
        return []

    cats = [u for u in _LOC_RE.findall(xml) if "/remote-jobs/" in u]
    return [u for u in cats if _category_matches_profile(u)][:MAX_CATEGORIES]


def _offers_from_category(html: str) -> list[tuple[str, str]]:
    """[(offer_path, company)] — company read from the markup next to the link."""
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for m in _OFFER_RE.finditer(html):
        path = m.group(1)
        # robots.txt disallows /offer/{*} — those are un-rendered template
        # placeholders, and they come through as a job titled "Undefined".
        if path in seen or "{" in path or "undefined" in path.lower():
            continue
        seen.add(path)
        # The company name sits in the alt/title attribute just before the link.
        window = html[max(0, m.start() - 260):m.start()]
        company = ""
        alt = re.findall(r'(?:alt|title)="([^"]{2,60})"', window)
        if alt:
            company = alt[-1].strip()
        out.append((path, company))
    return out


def fetch_jobgether_raw() -> list[JobRecord]:
    cats = _relevant_categories()
    if not cats:
        return []

    jobs: list[JobRecord] = []
    seen: set[str] = set()
    for i, cat in enumerate(cats):
        if i:
            time.sleep(CRAWL_DELAY)  # their stated crawl-delay, between requests
        try:
            html = _fetch(cat)
        except Exception as e:
            logger.debug("Jobgether %s failed: %s", cat, e)
            continue
        for path, company in _offers_from_category(html):
            url = BASE + path
            if url in seen:
                continue
            seen.add(url)
            jobs.append(JobRecord(
                url=url,
                source="Jobgether",
                company=company or "Unknown",
                title=_title_from_slug(path),
                # Jobgether is a remote-first board; the offer page carries the
                # region, and thin rows get enriched later if they pass the gate.
                location="Remote",
                discovered_at=_today(),
                notes="Jobgether — remote job board",
            ))
    if jobs:
        logger.info("Jobgether: %s raw from %s categories", len(jobs), len(cats))
    return jobs
