"""
Resolve a pasted Greenhouse / Lever / Ashby job URL to a job dict via public APIs.

No company-list membership required — only the URL.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

import requests

from scrapers.html_text import html_to_plain

logger = logging.getLogger(__name__)

FETCH_TIMEOUT = 12
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; shortlistr/1.0; job-url-resolver)",
    "Accept": "application/json",
}

ASHBY_GQL = "https://jobs.ashbyhq.com/api/non-user-graphql?op=ApiJobBoardWithTeams"
ASHBY_GQL_QUERY = """
query ApiJobBoardWithTeams($organizationHostedJobsPageName: String!) {
  jobBoard: jobBoardWithTeams(organizationHostedJobsPageName: $organizationHostedJobsPageName) {
    jobPostings {
      id
      title
      locationName
      isRemote
      externalLink
    }
  }
}
"""

# Greenhouse job-board URLs (hosted + API hosts)
_GH_JOB = re.compile(
    r"(?:boards-api|boards|job-boards)(?:\.eu)?\.greenhouse\.io/"
    r"(?:v1/boards/)?([^/?#]+)/jobs/(\d+)",
    re.I,
)
_LEVER_JOB = re.compile(
    r"jobs\.lever\.co/([^/?#]+)/([a-f0-9-]{36})",
    re.I,
)
_ASHBY_JOB = re.compile(
    r"jobs\.ashbyhq\.com/([^/?#]+)/([a-f0-9-]+)",
    re.I,
)


@dataclass(frozen=True)
class ParsedATS:
    ats_type: str  # greenhouse | lever | ashby
    slug: str
    job_id: str


def parse_ats_url(url: str) -> ParsedATS | None:
    """Extract ATS type, company slug, and job id from a job posting URL."""
    if not url or not url.startswith("http"):
        return None
    parsed = urlparse(url.strip())
    host_path = f"{parsed.netloc}{parsed.path}"

    m = _GH_JOB.search(host_path)
    if m:
        return ParsedATS("greenhouse", m.group(1).lower(), m.group(2))

    m = _LEVER_JOB.search(host_path)
    if m:
        return ParsedATS("lever", m.group(1).lower(), m.group(2).lower())

    m = _ASHBY_JOB.search(host_path)
    if m:
        return ParsedATS("ashby", m.group(1).lower(), m.group(2).lower())

    return None


def is_ats_job_url(url: str) -> bool:
    return parse_ats_url(url) is not None


def _job_dict(
    *,
    source: str,
    company: str,
    title: str,
    location: str,
    url: str,
    job_id: str,
    department: str = "",
    jd_snippet: str = "",
) -> dict[str, Any]:
    today = datetime.now().strftime("%Y-%m-%d")
    slug = company.lower().replace(" ", "-")
    return {
        "date_found": today,
        "source": source,
        "company": company,
        "title": title,
        "location": location,
        "url": url,
        "job_id": job_id,
        "department": department,
        "jd_snippet": jd_snippet[:800].strip(),
        "company_email": f"careers@{slug.replace('-', '')}.com",
        "status": "New",
        "email_sent": "No",
        "notes": "resolved from URL",
    }


def _fetch_greenhouse(slug: str, job_id: str, original_url: str) -> dict | None:
    api = f"https://api.greenhouse.io/v1/boards/{slug}/jobs/{job_id}?content=true"
    try:
        resp = requests.get(api, headers=HEADERS, timeout=FETCH_TIMEOUT)
        if resp.status_code != 200:
            return None
        job = resp.json()
    except Exception as e:
        logger.debug(f"Greenhouse resolve {slug}/{job_id}: {e}")
        return None

    title = job.get("title", "")
    if not title:
        return None
    location = (job.get("location") or {}).get("name", "")
    dept = ""
    if job.get("departments"):
        dept = job["departments"][0].get("name", "")
    return _job_dict(
        source="Greenhouse",
        company=slug.replace("-", " ").title(),
        title=title,
        location=location,
        url=job.get("absolute_url") or original_url,
        job_id=str(job.get("id", job_id)),
        department=dept,
        jd_snippet=html_to_plain(job.get("content", "") or "", max_len=800),
    )


def _fetch_lever(slug: str, job_id: str, original_url: str) -> dict | None:
    api = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    try:
        resp = requests.get(api, headers=HEADERS, timeout=FETCH_TIMEOUT)
        if resp.status_code != 200:
            return None
        postings = resp.json()
        if not isinstance(postings, list):
            return None
    except Exception as e:
        logger.debug(f"Lever resolve {slug}/{job_id}: {e}")
        return None

    for p in postings:
        if not isinstance(p, dict):
            continue
        pid = str(p.get("id", ""))
        if pid != job_id and p.get("hostedUrl", "") != original_url:
            continue
        cats = p.get("categories") or {}
        return _job_dict(
            source="Lever",
            company=slug.replace("-", " ").title(),
            title=p.get("text", ""),
            location=cats.get("location", "") or "",
            url=p.get("hostedUrl") or original_url,
            job_id=pid or job_id,
            department=cats.get("team", "") or "",
            jd_snippet=p.get("descriptionPlain", "") or "",
        )
    return None


def _fetch_ashby(slug: str, job_id: str, original_url: str) -> dict | None:
    # Fast path: public posting-api board
    board_url = (
        f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
        "?includeCompensation=true"
    )
    try:
        resp = requests.get(board_url, headers=HEADERS, timeout=FETCH_TIMEOUT)
        if resp.status_code == 200:
            for p in resp.json().get("jobs", []):
                if str(p.get("id", "")) == job_id:
                    return _job_dict(
                        source="Ashby",
                        company=slug.replace("-", " ").title(),
                        title=p.get("title", ""),
                        location=p.get("location", "") or "Remote",
                        url=p.get("jobUrl") or original_url,
                        job_id=job_id,
                        jd_snippet=p.get("descriptionPlain", "") or "",
                    )
    except Exception:
        pass

    # GraphQL fallback
    try:
        payload = {
            "operationName": "ApiJobBoardWithTeams",
            "query": ASHBY_GQL_QUERY,
            "variables": {"organizationHostedJobsPageName": slug},
        }
        resp = requests.post(
            ASHBY_GQL, json=payload,
            headers={**HEADERS, "Content-Type": "application/json"},
            timeout=FETCH_TIMEOUT,
        )
        if resp.status_code != 200:
            return None
        postings = (
            resp.json().get("data", {}).get("jobBoard", {}).get("jobPostings", [])
        )
        for p in postings:
            if str(p.get("id", "")) != job_id:
                continue
            loc = p.get("locationName", "") or ("Remote" if p.get("isRemote") else "")
            return _job_dict(
                source="Ashby",
                company=slug.replace("-", " ").title(),
                title=p.get("title", ""),
                location=loc,
                url=p.get("externalLink") or original_url,
                job_id=job_id,
            )
    except Exception as e:
        logger.debug(f"Ashby resolve {slug}/{job_id}: {e}")
    return None


_KNOWN_CAREERS_HOSTS: dict[str, tuple[str, str]] = {
    "careers.datadoghq.com": (
        "Datadog",
        r"<title>\s*([^|<]+?)\s*\|\s*Datadog",
    ),
    "www.kentik.com": (
        "Kentik",
        r'content="([^"]+)\s*\|\s*Career',
    ),
}


def _is_known_careers_url(url: str) -> bool:
    if not url:
        return False
    host = urlparse(url.strip()).netloc.lower()
    return host in _KNOWN_CAREERS_HOSTS


def can_resolve_job_url(url: str) -> bool:
    """True if URL can be resolved via ATS API or known careers-page scrape."""
    return is_ats_job_url(url) or _is_known_careers_url(url)


def _resolve_careers_html(url: str) -> dict | None:
    """Scrape title + JD from company careers pages (Datadog, Kentik, etc.)."""
    parsed = urlparse(url.strip())
    host = parsed.netloc.lower()
    spec = _KNOWN_CAREERS_HOSTS.get(host)
    if not spec:
        return None
    company_label, title_pat = spec
    try:
        from scrapers.browser_fetch import fetch_page
        from scrapers.html_text import html_to_markdown, html_to_plain

        page = fetch_page(url.strip(), allow_browser=False)
        if page.status != 200 or not page.html:
            return None
        html = page.html
        md = html_to_markdown(html, max_len=12000)
        jd = html_to_plain(md, max_len=4000)
    except Exception as e:
        logger.debug(f"Careers HTML resolve {url}: {e}")
        return None

    title = ""
    m = re.search(title_pat, html, re.I | re.S)
    if m:
        title = re.sub(r"\s+", " ", m.group(1)).strip()
    if not title:
        m = re.search(r"<title>\s*([^<|]+)", html, re.I)
        if m:
            title = m.group(1).strip()

    if not title:
        return None

    return _job_dict(
        source="Careers",
        company=company_label,
        title=title,
        location="Remote",
        url=page.final_url or url,
        job_id=parsed.path.rstrip("/").split("/")[-1] or "0",
        jd_snippet=jd[:800],
    )


def resolve_job_url(url: str) -> dict | None:
    """Fetch job metadata for ATS or known careers posting URLs."""
    parsed = parse_ats_url(url)
    if parsed:
        if parsed.ats_type == "greenhouse":
            return _fetch_greenhouse(parsed.slug, parsed.job_id, url)
        if parsed.ats_type == "lever":
            return _fetch_lever(parsed.slug, parsed.job_id, url)
        if parsed.ats_type == "ashby":
            return _fetch_ashby(parsed.slug, parsed.job_id, url)

    return _resolve_careers_html(url)


def resolve_job_urls(urls: list[str]) -> list[dict]:
    """Resolve multiple ATS URLs; skip failures and duplicates."""
    jobs: list[dict] = []
    seen: set[str] = set()
    for url in urls:
        url = url.strip().split("?")[0]
        if not url or url in seen:
            continue
        job = resolve_job_url(url)
        if job:
            key = job.get("url") or job.get("job_id", "")
            if key not in seen:
                seen.add(key)
                jobs.append(job)
    return jobs
