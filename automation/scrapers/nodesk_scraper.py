"""
NoDesk Scraper — requests + HTML parse (no Playwright needed, no auth).
Jobs at: https://nodesk.co/remote-jobs/engineering/
"""

import requests
import logging
import re
from datetime import datetime
from config import SEARCH_KEYWORDS

logger = logging.getLogger(__name__)

PAGES = [
    "https://nodesk.co/remote-jobs/engineering/",
    "https://nodesk.co/remote-jobs/devops/",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
}

def _extract_jobs(html: str, source_url: str) -> list[dict]:
    jobs = []
    today = datetime.now().strftime("%Y-%m-%d")
    # Match job card anchors: href="/remote-jobs/job/..."
    pattern = re.compile(
        r'href="(/remote-jobs/[^"]+)"[^>]*>.*?<h2[^>]*>([^<]+)</h2>.*?<span[^>]*>([^<]+)</span>',
        re.DOTALL,
    )
    for m in pattern.finditer(html):
        href, title, company = m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
        if not any(kw in title.lower() for kw in SEARCH_KEYWORDS):
            continue
        jobs.append({
            "date_found":    today,
            "source":        "NoDesk",
            "company":       company,
            "title":         title,
            "location":      "Remote",
            "url":           f"https://nodesk.co{href}",
            "job_id":        href,
            "department":    "",
            "jd_snippet":    "",
            "salary":        "",
            "company_email": "",
            "status":        "New",
            "email_sent":    "No",
            "notes":         "",
        })
    return jobs


def scrape_nodesk() -> list[dict]:
    jobs = []
    seen = set()
    for url in PAGES:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code != 200:
                logger.warning(f"NoDesk {url}: HTTP {resp.status_code}")
                continue
            for job in _extract_jobs(resp.text, url):
                if job["job_id"] not in seen:
                    seen.add(job["job_id"])
                    jobs.append(job)
        except Exception as e:
            logger.warning(f"NoDesk {url} error: {e}")

    logger.info(f"NoDesk: {len(jobs)} matching jobs")
    return jobs
