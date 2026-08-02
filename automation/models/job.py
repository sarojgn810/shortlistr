"""Canonical job record used across discovery, store, and eval."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def job_id_from_url(url: str) -> str:
    """Stable 16-hex id from a job URL.

    Query strings are normally stripped so tracking params do not fork
    duplicates. Boards that put the *job identity* in the query (Glassdoor
    partner links, some Indeed click-trackers) must keep that key — otherwise
    every listing in a digest collapses to one DB row.
    """
    from urllib.parse import parse_qs, urlparse

    raw = (url or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    base = f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")
    host = (parsed.netloc or "").lower()
    path = (parsed.path or "").lower()
    qs = parse_qs(parsed.query or "")

    identity = base
    if "glassdoor." in host and "joblisting" in path:
        jid = (qs.get("jobListingId") or qs.get("joblistingid") or [""])[0]
        if jid:
            identity = f"{base}?jobListingId={jid}"
    elif "cts.indeed.com" in host and parsed.query:
        # Indeed email digests wrap destinations in cts trackers; keep the
        # full query so distinct clicks stay distinct.
        identity = f"{base}?{parsed.query}"

    return hashlib.sha256(identity.encode()).hexdigest()[:16]


@dataclass
class JobRecord:
    url: str
    source: str
    company: str
    title: str
    location: str = ""
    jd_text: str = ""
    salary: str = ""
    department: str = ""
    company_email: str = ""
    status: str = "New"
    email_sent: str = "No"
    notes: str = ""
    fit_score: int = 0
    fit_reason: str = ""
    discovered_at: str = ""
    job_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.discovered_at:
            self.discovered_at = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        # The canonical id is ALWAYS the URL hash. A source-provided job_id
        # (RemoteOK numeric id, WeWorkRemotely guid=URL, NoDesk/Jobspresso href,
        # …) must never become the DB key, or it fails the API's 16-hex
        # validation and the job becomes non-actionable. Keep the source id in
        # metadata for traceability.
        canonical = job_id_from_url(self.url)
        if canonical:
            if self.job_id and self.job_id != canonical:
                self.metadata.setdefault("source_job_id", self.job_id)
            self.job_id = canonical
        elif not self.job_id:
            self.job_id = ""

    def to_dict(self) -> dict[str, Any]:
        """Legacy dict shape for tracker, email, and existing processors."""
        d = asdict(self)
        d["date_found"] = self.discovered_at
        d["jd_snippet"] = self.jd_text[:800] if self.jd_text else ""
        d["description"] = self.jd_text
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JobRecord:
        return cls(
            url=data.get("url", ""),
            source=data.get("source", ""),
            company=data.get("company", ""),
            title=data.get("title", ""),
            location=data.get("location", ""),
            jd_text=data.get("jd_text") or data.get("jd_snippet") or data.get("description", "") or "",
            salary=data.get("salary", ""),
            department=data.get("department", ""),
            company_email=data.get("company_email", ""),
            status=data.get("status", "New"),
            email_sent=data.get("email_sent", "No"),
            notes=data.get("notes", ""),
            fit_score=int(data.get("fit_score", 0) or 0),
            fit_reason=data.get("fit_reason", ""),
            discovered_at=data.get("discovered_at") or data.get("date_found", ""),
            job_id=str(data.get("job_id", "") or ""),
            metadata=dict(data.get("metadata") or {}),
        )

    def to_json(self) -> str:
        return json.dumps(asdict(self), default=str)
