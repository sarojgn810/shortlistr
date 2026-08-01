"""Recruitee public offers API — no auth."""

from __future__ import annotations

import logging
import time
from datetime import datetime

import requests

from models.job import JobRecord
from portals_config import get_recruitee_slugs
from sources.base import FetchStats, SourceAdapter

logger = logging.getLogger(__name__)

# Fallback when portals.yml has no Recruitee boards yet.
DEFAULT_RECRUITEE = ["remote", "doctolib", "mirakl"]


def _fetch_slug(slug: str) -> list[JobRecord]:
    today = datetime.now().strftime("%Y-%m-%d")
    url = f"https://{slug}.recruitee.com/api/offers"
    try:
        resp = requests.get(url, timeout=12)
        if resp.status_code != 200:
            return []
        data = resp.json() or {}
    except Exception as exc:
        logger.debug("Recruitee %s: %s", slug, exc)
        return []
    offers = data.get("offers") if isinstance(data, dict) else data
    if not isinstance(offers, list):
        return []
    out: list[JobRecord] = []
    for o in offers:
        if not isinstance(o, dict):
            continue
        title = str(o.get("title") or "")
        loc = o.get("location") or o.get("city") or ""
        if isinstance(loc, dict):
            loc = loc.get("city") or loc.get("name") or ""
        href = str(o.get("careers_url") or o.get("url") or "")
        if href and not href.startswith("http"):
            href = f"https://{slug}.recruitee.com{href}"
        if not href:
            oid = o.get("id") or o.get("slug") or ""
            href = f"https://{slug}.recruitee.com/o/{oid}"
        out.append(
            JobRecord(
                url=href,
                source="Recruitee",
                company=str(o.get("company_name") or slug.replace("-", " ").title()),
                title=title,
                location=str(loc) or "",
                jd_text=str(o.get("description") or o.get("body") or "")[:8000],
                discovered_at=today,
                metadata={"slug": slug},
            )
        )
    return out


class RecruiteeAdapter(SourceAdapter):
    name = "recruitee"

    def fetch_raw(self, log_totals: bool = False) -> tuple[list[JobRecord], FetchStats]:
        stats = FetchStats(source=self.name)
        t0 = time.monotonic()
        slugs = list(get_recruitee_slugs()) or list(DEFAULT_RECRUITEE)
        jobs: list[JobRecord] = []
        for slug in slugs:
            jobs.extend(_fetch_slug(slug))
        stats.raw_count = len(jobs)
        stats.duration_ms = int((time.monotonic() - t0) * 1000)
        if log_totals:
            logger.info("Recruitee: %s slugs → %s raw", len(slugs), stats.raw_count)
        return jobs, stats
