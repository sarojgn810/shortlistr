"""Which apply channel a posting actually supports.

Aggregator and login-walled listings (LinkedIn, Naukri, Indeed, …) serve a job
*ad*, not an application form a browser can fill. This repo has no Easy Apply /
auto-apply path for them by design, so those postings are link-only: open the
posting and apply on the site yourself.
"""

from __future__ import annotations

from urllib.parse import urlparse


class NotFillableError(ValueError):
    """Raised when apply-assist is asked to fill a link-only posting."""


LINK_ONLY_HOSTS = (
    "linkedin.com",
    "naukri.com",
    "indeed.com",
    "glassdoor.com",
    "glassdoor.co.in",
    "monster.com",
    "foundit.in",
    "shine.com",
    "timesjobs.com",
    "dice.com",
    "ziprecruiter.com",
    "simplyhired.com",
    "instahyre.com",
    "hirist.tech",
    "hirist.com",
    "cutshort.io",
    "iimjobs.com",
    "wellfound.com",
    "angel.co",
)

# Adapters label rows with a display name ("Naukri", "LinkedIn Guest",
# "Apify:linkedin"), so match loosely on the board name.
LINK_ONLY_SOURCE_KEYWORDS = (
    "linkedin",
    "naukri",
    "indeed",
    "glassdoor",
    "monster",
    "foundit",
    "shine",
    "timesjobs",
    "dice",
    "ziprecruiter",
    "instahyre",
    "hirist",
    "cutshort",
    "iimjobs",
    "wellfound",
)


def _host_of(url: str) -> str:
    host = urlparse(url or "").netloc.lower().split(":")[0]
    return host[4:] if host.startswith("www.") else host


def is_link_only(url: str = "", source: str = "") -> bool:
    """True when the posting can only be opened, not pre-filled."""
    host = _host_of(url)
    if host and any(host == h or host.endswith("." + h) for h in LINK_ONLY_HOSTS):
        return True
    src = (source or "").lower()
    return any(keyword in src for keyword in LINK_ONLY_SOURCE_KEYWORDS)


LINK_ONLY_MESSAGE = (
    "This posting lives on a job board that has no fillable application form "
    "(LinkedIn, Naukri and similar). Open the posting and apply there."
)


def application_url(job_row) -> str:
    """The URL to actually apply at, which is not always the URL we listed.

    Aggregators publish a job under their own address and carry the employer's
    application link alongside it. LinkedIn accounts for most of this pipeline
    and none of its listing pages have a form on them, so filling anything at
    all depends on preferring the employer's link when the source gave us one.

    Falls back to the listing URL, which is the right behaviour for postings
    scraped straight from an ATS — there the two are the same thing.
    """
    import json

    try:
        raw = job_row["metadata_json"]
    except Exception:
        raw = None

    if raw:
        try:
            apply_url = str((json.loads(raw) or {}).get("apply_url") or "").strip()
        except Exception:
            apply_url = ""
        if apply_url.startswith(("http://", "https://")):
            return apply_url

    try:
        return str(job_row["url"] or "")
    except Exception:
        return ""
