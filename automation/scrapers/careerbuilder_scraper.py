"""
CareerBuilder Scraper — requests (no account needed).
API: https://www.careerbuilder.com/jobs?keywords=site+reliability+engineer&location=remote
"""

import requests
import logging
import re
from datetime import datetime
from config import SEARCH_KEYWORDS

logger = logging.getLogger(__name__)

BASE_URL = "https://www.careerbuilder.com/jobs"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}

QUERIES = [
    "site reliability engineer",
    "devops engineer",
    "platform engineer",
    "aiops engineer",
    "mlops engineer",
]

def scrape_careerbuilder() -> list[dict]:
    jobs = []
    today = datetime.now().strftime("%Y-%m-%d")
    seen = set()

    for q in QUERIES:
        params = {"keywords": q, "location": "remote", "posted": "3"}  # last 3 days
        try:
            resp = requests.get(BASE_URL, params=params, headers=HEADERS, timeout=15)
            if resp.status_code != 200:
                logger.warning(f"CareerBuilder '{q}': HTTP {resp.status_code}")
                continue
            html = resp.text
        except Exception as e:
            logger.warning(f"CareerBuilder '{q}' error: {e}")
            continue

        # CareerBuilder job cards contain data-job-did attribute
        pattern = re.compile(
            r'data-job-did="([^"]+)".*?<div[^>]+class="[^"]*job-title[^"]*"[^>]*><a[^>]+>([^<]+)</a>.*?<div[^>]+class="[^"]*company[^"]*"[^>]*>([^<]+)</div>',
            re.DOTALL,
        )
        for m in pattern.finditer(html):
            job_id, title, company = m.group(1), m.group(2).strip(), m.group(3).strip()
            if not any(kw in title.lower() for kw in SEARCH_KEYWORDS):
                continue
            if job_id in seen:
                continue
            seen.add(job_id)

            jobs.append({
                "date_found":    today,
                "source":        "CareerBuilder",
                "company":       company,
                "title":         title,
                "location":      "Remote",
                "url":           f"https://www.careerbuilder.com/job/{job_id}",
                "job_id":        job_id,
                "department":    "",
                "jd_snippet":    "",
                "salary":        "",
                "company_email": "",
                "status":        "New",
                "email_sent":    "No",
                "notes":         "",
            })

    logger.info(f"CareerBuilder: {len(jobs)} matching jobs")
    return jobs
