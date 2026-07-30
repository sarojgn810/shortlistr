"""
Lever ATS Scraper — public API, raw fetch.
Filtering happens in pipeline/filter.py.
"""

import logging

from models.job import JobRecord
from pipeline.filter import apply_discovery_filter
from portals_config import get_lever_slugs
from sources.fetcher import cached_get_json
from sources.parallel import parallel_flat_map

logger = logging.getLogger(__name__)


def _extract_description(p: dict) -> str:
    desc_body = p.get("descriptionBody", "")
    if isinstance(desc_body, dict):
        desc = ""
        for block in desc_body.get("content", []):
            if not isinstance(block, dict):
                continue
            for node in block.get("content", []):
                if isinstance(node, dict) and node.get("type") == "text":
                    desc += node.get("text", "") + " "
        if desc.strip():
            return desc.strip()
    plain = p.get("descriptionPlain", "") or ""
    if plain.strip():
        return plain.strip()
    if isinstance(desc_body, str) and desc_body.strip():
        return desc_body.strip()
    return ""


def _fetch_lever_slug(slug: str) -> list[JobRecord]:
    url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    data = cached_get_json(url, cache_key=f"lever/{slug}", timeout=12)
    if not isinstance(data, list):
        return []

    jobs: list[JobRecord] = []
    for p in data:
        if not isinstance(p, dict):
            continue
        cats = p.get("categories") or {}
        jobs.append(
            JobRecord(
                url=p.get("hostedUrl", ""),
                source="Lever",
                company=slug.replace("-", " ").title(),
                title=p.get("text", ""),
                location=cats.get("location", "") or "",
                jd_text=_extract_description(p),
                department=cats.get("team", "") or "",
                company_email=f"careers@{slug.replace('-', '')}.com",
                job_id=str(p.get("id", "")),
                metadata={"slug": slug},
            )
        )
    return jobs


def fetch_lever_raw(companies: list | None = None) -> list[JobRecord]:
    slugs = companies or get_lever_slugs()
    return parallel_flat_map(slugs, _fetch_lever_slug, max_workers=10)


def scrape_lever(companies: list = None, log_totals: bool = False) -> list[dict]:
    raw = fetch_lever_raw(companies)
    if log_totals:
        logger.info(f"Lever: {len(raw)} raw (unfiltered)")
    passed, _, _ = apply_discovery_filter(raw)
    if log_totals:
        logger.info(f"Lever total: {len(raw)} raw → {len(passed)} after discovery filter")
    return [j.to_dict() for j in passed]
