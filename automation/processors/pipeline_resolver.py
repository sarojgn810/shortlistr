"""Helpers for resolving ATS jobs from pipeline and email URLs."""

from __future__ import annotations

import os
import re

from config import PIPELINE_PATH
from scrapers.ats_url_resolver import is_ats_job_url, resolve_job_urls


_PENDING_URL = re.compile(r"- \[[ x]\] (https?://\S+)")


def extract_pending_urls(pipeline_path: str | None = None) -> list[str]:
    """Return URLs from ## Pending lines in pipeline.md."""
    path = pipeline_path or PIPELINE_PATH
    if not os.path.exists(path):
        return []
    urls: list[str] = []
    in_pending = False
    for line in open(path, encoding="utf-8"):
        stripped = line.strip()
        if stripped.startswith("## "):
            in_pending = stripped.lower().startswith("## pending") or stripped == "## Pendientes"
            continue
        if not in_pending:
            continue
        m = _PENDING_URL.match(stripped)
        if m:
            url = m.group(1).split("|")[0].strip()
            if url.startswith("http"):
                urls.append(url)
    return urls


def resolve_pending_ats_jobs(pipeline_path: str | None = None) -> list[dict]:
    """Resolve ATS posting URLs from pipeline pending section."""
    ats_urls = [u for u in extract_pending_urls(pipeline_path) if is_ats_job_url(u)]
    return resolve_job_urls(ats_urls)
