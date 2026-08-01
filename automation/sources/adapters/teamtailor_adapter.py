"""Teamtailor public job-board feed — often includes recruiter name/email."""

from __future__ import annotations

import logging
import time
from datetime import datetime

import requests

from models.job import JobRecord
from portals_config import get_teamtailor_slugs
from sources.base import FetchStats, SourceAdapter

logger = logging.getLogger(__name__)

DEFAULT_SLUGS: list[str] = []  # portals.yml only — no noisy defaults


def _slug_from_url(url: str) -> str | None:
    import re

    m = re.search(r"https?://([a-z0-9-]+)\.teamtailor\.com", url or "", re.I)
    return m.group(1) if m else None


def _fetch_slug(slug: str) -> list[JobRecord]:
    today = datetime.now().strftime("%Y-%m-%d")
    # Public JSON: https://{slug}.teamtailor.com/jobs.json or careers API
    urls = [
        f"https://{slug}.teamtailor.com/jobs.json",
        f"https://api.teamtailor.com/v1/jobs?filter[company]={slug}",
    ]
    jobs: list[JobRecord] = []
    for url in urls:
        try:
            resp = requests.get(
                url,
                timeout=12,
                headers={"User-Agent": "AutojobTeamtailor/1.0", "Accept": "application/json"},
            )
            if resp.status_code != 200:
                continue
            data = resp.json()
        except Exception as exc:
            logger.debug("Teamtailor %s: %s", slug, exc)
            continue
        items = []
        if isinstance(data, dict):
            items = data.get("jobs") or data.get("data") or data.get("results") or []
        elif isinstance(data, list):
            items = data
        for j in items:
            if not isinstance(j, dict):
                continue
            # Normalize Teamtailor / JSON:API shapes
            attrs = j.get("attributes") if isinstance(j.get("attributes"), dict) else j
            title = str(attrs.get("title") or j.get("title") or "")
            href = str(
                attrs.get("url")
                or j.get("url")
                or j.get("links", {}).get("careersite-job-url")
                or ""
            )
            if href and not href.startswith("http"):
                href = f"https://{slug}.teamtailor.com{href}"
            if not href:
                jid = j.get("id") or attrs.get("id") or ""
                href = f"https://{slug}.teamtailor.com/jobs/{jid}"
            loc = attrs.get("locations") or attrs.get("location") or ""
            if isinstance(loc, list) and loc:
                loc = loc[0]
            if isinstance(loc, dict):
                loc = loc.get("name") or loc.get("city") or ""
            recruiter = attrs.get("recruiter") or j.get("recruiter") or {}
            meta: dict = {"slug": slug, "ats": "teamtailor"}
            if isinstance(recruiter, dict) and (recruiter.get("email") or recruiter.get("name")):
                meta["recruiter"] = {
                    "name": recruiter.get("name")
                    or f"{recruiter.get('first_name', '')} {recruiter.get('last_name', '')}".strip(),
                    "email": recruiter.get("email") or "",
                    "title": recruiter.get("title") or "Recruiter",
                }
            jobs.append(
                JobRecord(
                    url=href,
                    source="Teamtailor",
                    company=str(attrs.get("company_name") or slug.replace("-", " ").title()),
                    title=title,
                    location=str(loc or ""),
                    jd_text=str(attrs.get("body") or attrs.get("description") or "")[:8000],
                    discovered_at=today,
                    metadata=meta,
                )
            )
        if jobs:
            break
    return jobs


class TeamtailorAdapter(SourceAdapter):
    name = "teamtailor"

    def fetch_raw(self, log_totals: bool = False) -> tuple[list[JobRecord], FetchStats]:
        stats = FetchStats(source=self.name)
        t0 = time.monotonic()
        slugs = list(get_teamtailor_slugs()) or list(DEFAULT_SLUGS)
        jobs: list[JobRecord] = []
        for slug in slugs:
            jobs.extend(_fetch_slug(slug))
        stats.raw_count = len(jobs)
        stats.duration_ms = int((time.monotonic() - t0) * 1000)
        if log_totals:
            logger.info("Teamtailor: %s slugs → %s raw", len(slugs), stats.raw_count)
        return jobs, stats
