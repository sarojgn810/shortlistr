"""Soft dedupe — same company + title + location across ATS hosts.

URL-hash ``job_id`` still wins for exact URL identity. Soft keys collapse
cross-board reposts (Greenhouse vs LinkedIn guest, etc.) preferring the richer JD.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from models.job import JobRecord

_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[^\w\s+.#/-]", re.UNICODE)


def soft_key(company: str, title: str, location: str) -> str:
    def norm(s: str) -> str:
        s = (s or "").strip().lower()
        s = _PUNCT.sub(" ", s)
        s = _WS.sub(" ", s).strip()
        return s

    c, t, loc = norm(company), norm(title), norm(location)
    if not c or not t:
        return ""
    return f"{c}|{t}|{loc}"


def _richness(job: JobRecord) -> tuple[int, int, int]:
    jd = (job.jd_text or "").strip()
    return (
        len(jd),
        1 if (job.company_email or "").strip() else 0,
        int(job.fit_score or 0),
    )


def collapse_soft_duplicates(jobs: list[JobRecord]) -> list[JobRecord]:
    """Keep one job per soft key; prefer longer JD / email / fit."""
    if not jobs:
        return []
    best: dict[str, JobRecord] = {}
    for j in jobs:
        key = soft_key(j.company or "", j.title or "", j.location or "")
        if not key:
            continue
        prev = best.get(key)
        if prev is None or _richness(j) > _richness(prev):
            best[key] = j
    # Preserve first-seen order among winners + unkeyed
    seen: set[str] = set()
    out: list[JobRecord] = []
    for j in jobs:
        key = soft_key(j.company or "", j.title or "", j.location or "")
        if not key:
            out.append(j)
            continue
        winner = best.get(key)
        if winner is None:
            continue
        wid = winner.job_id or winner.url
        if wid in seen:
            continue
        if (j.job_id or j.url) == wid:
            out.append(winner)
            seen.add(wid)
    return out
