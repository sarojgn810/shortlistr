"""Public job APIs — Adzuna, Arbeitnow, Jobicy.

Official documented endpoints, not scrapes. Arbeitnow and Jobicy need no
credentials at all; Adzuna needs a free app id/key and is the only one of the
three with a real India index, which matters for a profile targeting Bangalore.

Each feed is small and independent, so they run together and a dead one never
takes the source down with it. Yield is honest rather than exciting: measured
against a Site Reliability Engineer profile, Arbeitnow returned 2 matches out of
175 postings and Jobicy 2 out of 100. They are worth having because they are
free and cost one request each, not because they will fill an inbox.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any

from models.job import JobRecord
from sources.base import FetchStats, SourceAdapter

logger = logging.getLogger(__name__)

ARBEITNOW_URL = "https://www.arbeitnow.com/api/job-board-api"
JOBICY_URL = "https://jobicy.com/api/v2/remote-jobs?count=100"
ADZUNA_URL = "https://api.adzuna.com/v1/api/jobs/{country}/search/1"

# Adzuna indexes by country. Derived from the profile's locations so an Indian
# search hits adzuna.in rather than the US index.
_COUNTRY_BY_KEYWORD = {
    "india": "in", "bangalore": "in", "bengaluru": "in", "mumbai": "in",
    "hyderabad": "in", "pune": "in", "chennai": "in", "delhi": "in",
    "united states": "us", "usa": "us", "america": "us",
    "united kingdom": "gb", "britain": "gb", "england": "gb", "london": "gb",
    "canada": "ca", "australia": "au", "germany": "de", "france": "fr",
    "netherlands": "nl", "singapore": "sg", "poland": "pl", "brazil": "br",
}


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _profile_titles() -> list[str]:
    import config as cfg

    titles = [t.strip() for t in (getattr(cfg, "SEARCH_KEYWORDS", None) or []) if t and t.strip()]
    return sorted(dict.fromkeys(titles), key=len, reverse=True)[:3]


def _adzuna_country() -> str:
    import config as cfg

    for kw in (getattr(cfg, "LOCATION_KEYWORDS", None) or []):
        hit = _COUNTRY_BY_KEYWORD.get(str(kw).lower().strip())
        if hit:
            return hit
    return "gb"  # Adzuna's own default index; never guess a user's country


def fetch_arbeitnow() -> list[JobRecord]:
    from sources.fetcher import cached_get_json

    data = cached_get_json(ARBEITNOW_URL, timeout=12)
    rows = (data or {}).get("data") if isinstance(data, dict) else None
    out: list[JobRecord] = []
    for j in rows or []:
        url = (j.get("url") or "").strip()
        if not url:
            continue
        location = (j.get("location") or "").strip()
        if j.get("remote") and "remote" not in location.lower():
            location = f"{location}, Remote".strip(", ")
        out.append(JobRecord(
            url=url,
            source="Arbeitnow",
            company=(j.get("company_name") or "").strip(),
            title=(j.get("title") or "").strip(),
            location=location,
            jd_text=(j.get("description") or "")[:4000],
            discovered_at=_today(),
            notes="Arbeitnow — public job API",
        ))
    return out


def fetch_jobicy() -> list[JobRecord]:
    from sources.fetcher import cached_get_json

    data = cached_get_json(JOBICY_URL, timeout=12)
    rows = (data or {}).get("jobs") if isinstance(data, dict) else None
    out: list[JobRecord] = []
    for j in rows or []:
        url = (j.get("url") or "").strip()
        if not url:
            continue
        # jobGeo is a region list like "EMEA,  Italy", or "Anywhere".
        geo = " ".join((j.get("jobGeo") or "").split()).strip()
        out.append(JobRecord(
            url=url,
            source="Jobicy",
            company=(j.get("companyName") or "").strip(),
            title=(j.get("jobTitle") or "").strip(),
            location=geo or "Remote",
            jd_text=(j.get("jobExcerpt") or "")[:4000],
            discovered_at=_today(),
            notes="Jobicy — public remote job API",
        ))
    return out


def fetch_adzuna() -> list[JobRecord]:
    """Adzuna needs a free app id + key. Silent no-op when unconfigured."""
    from secrets_store import get_secret
    from sources.fetcher import cached_get_json

    app_id = get_secret("ADZUNA_APP_ID")
    app_key = get_secret("ADZUNA_APP_KEY")
    if not (app_id and app_key):
        return []

    country = _adzuna_country()
    out: list[JobRecord] = []
    seen: set[str] = set()
    for title in _profile_titles() or [""]:
        # One query per target title, same reasoning as the ATS sources: a single
        # query would hide every other role the profile asks for.
        url = (
            f"{ADZUNA_URL.format(country=country)}"
            f"?app_id={app_id}&app_key={app_key}&results_per_page=50"
            f"&what={title.replace(' ', '%20')}&content-type=application/json"
        )
        data = cached_get_json(url, cache_key=f"adzuna/{country}/{title}", timeout=15)
        for j in ((data or {}).get("results") if isinstance(data, dict) else None) or []:
            link = (j.get("redirect_url") or "").strip()
            if not link or link in seen:
                continue
            seen.add(link)
            out.append(JobRecord(
                url=link,
                source="Adzuna",
                company=((j.get("company") or {}).get("display_name") or "").strip(),
                title=(j.get("title") or "").strip(),
                location=((j.get("location") or {}).get("display_name") or "").strip(),
                jd_text=(j.get("description") or "")[:4000],
                discovered_at=_today(),
                notes="Adzuna — public job API",
            ))
    return out


def fetch_jobgether() -> list[JobRecord]:
    """Jobgether — crawled via their sitemap at their stated Crawl-delay.

    Jobsora is deliberately absent: its robots.txt disallows /vacancy/,
    /vacancy-search/ and every query-string URL, which is every path that has a
    job on it. There is no permitted way in, so it is not built.
    """
    from scrapers.jobgether_scraper import fetch_jobgether_raw

    return fetch_jobgether_raw()


_FEEDS: tuple[tuple[str, Any], ...] = (
    ("Arbeitnow", fetch_arbeitnow),
    ("Jobicy", fetch_jobicy),
    ("Adzuna", fetch_adzuna),
    ("Jobgether", fetch_jobgether),
)


class PublicFeedsAdapter(SourceAdapter):
    name = "public_feeds"

    def fetch_raw(self, log_totals: bool = False) -> tuple[list[JobRecord], FetchStats]:
        from sources.parallel import parallel_call

        t0 = time.monotonic()
        stats = FetchStats(source=self.name)

        def _one(label: str, fn):
            def run() -> list[JobRecord]:
                try:
                    rows = fn()
                except Exception as e:
                    # One dead feed must never empty the source.
                    logger.warning("%s feed failed: %s", label, e)
                    return []
                if log_totals:
                    logger.info("%s: %s raw", label, len(rows))
                return rows

            return run

        jobs: list[JobRecord] = []
        for chunk in parallel_call([_one(lbl, fn) for lbl, fn in _FEEDS]):
            jobs.extend(chunk)

        stats.raw_count = len(jobs)
        stats.duration_ms = int((time.monotonic() - t0) * 1000)
        return jobs, stats
