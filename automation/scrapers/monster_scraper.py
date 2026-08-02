"""
Monster Scraper — requests (no account needed).
API: https://www.monster.com/jobs/search?q=site-reliability-engineer&where=remote
"""

import requests
import logging
import re
from datetime import datetime
from config import SEARCH_KEYWORDS

logger = logging.getLogger(__name__)

BASE_URL = "https://www.monster.com/jobs/search"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}

QUERIES = [
    "site-reliability-engineer",
    "devops-engineer",
    "platform-engineer",
    "aiops-engineer",
]

def scrape_monster() -> list[dict]:
    jobs = []
    today = datetime.now().strftime("%Y-%m-%d")
    seen = set()

    for q in QUERIES:
        params = {"q": q, "where": "remote", "recency": "last+week"}
        try:
            resp = requests.get(BASE_URL, params=params, headers=HEADERS, timeout=15)
            if resp.status_code != 200:
                logger.warning(f"Monster '{q}': HTTP {resp.status_code}")
                continue
            html = resp.text
        except Exception as e:
            logger.warning(f"Monster '{q}' error: {e}")
            continue

        # Monster embeds job data in JSON-LD or data attributes
        pattern = re.compile(
            r'"jobId"\s*:\s*"([^"]+)".*?"jobTitle"\s*:\s*"([^"]+)".*?"companyName"\s*:\s*"([^"]+)".*?"applyUrl"\s*:\s*"([^"]+)"',
            re.DOTALL,
        )
        for m in pattern.finditer(html):
            job_id, title, company, url = m.group(1), m.group(2), m.group(3), m.group(4)
            if not any(kw in title.lower() for kw in SEARCH_KEYWORDS):
                continue
            if job_id in seen:
                continue
            seen.add(job_id)

            jobs.append({
                "date_found":    today,
                "source":        "Monster",
                "company":       company,
                "title":         title,
                "location":      "Remote",
                "url":           url,
                "job_id":        job_id,
                "department":    "",
                "jd_snippet":    "",
                "salary":        "",
                "company_email": "",
                "status":        "New",
                "email_sent":    "No",
                "notes":         "",
            })

    logger.info(f"Monster: {len(jobs)} matching jobs")
    return jobs
