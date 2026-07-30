"""
Jobspresso Scraper — requests (no auth, no Playwright).
Jobs at: https://jobspresso.co/remote-work/
"""

import requests
import logging
import re
from datetime import datetime
from config import SEARCH_KEYWORDS

logger = logging.getLogger(__name__)

BASE_URL = "https://jobspresso.co/remote-work/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
}

def scrape_jobspresso() -> list[dict]:
    jobs = []
    today = datetime.now().strftime("%Y-%m-%d")
    seen = set()

    try:
        resp = requests.get(BASE_URL, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            logger.warning(f"Jobspresso: HTTP {resp.status_code}")
            return jobs
        html = resp.text
    except Exception as e:
        logger.warning(f"Jobspresso fetch error: {e}")
        return jobs

    # Extract job cards: <li class="job_listing ...">
    card_pattern = re.compile(
        r'href="(https://jobspresso\.co/[^"]+)"[^>]*>.*?<h3[^>]*>([^<]+)</h3>.*?<strong[^>]*>([^<]+)</strong>',
        re.DOTALL,
    )
    for m in card_pattern.finditer(html):
        href, title, company = m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
        if not any(kw in title.lower() for kw in SEARCH_KEYWORDS):
            continue
        if href in seen:
            continue
        seen.add(href)
        jobs.append({
            "date_found":    today,
            "source":        "Jobspresso",
            "company":       company,
            "title":         title,
            "location":      "Remote",
            "url":           href,
            "job_id":        href,
            "department":    "",
            "jd_snippet":    "",
            "salary":        "",
            "company_email": "",
            "status":        "New",
            "email_sent":    "No",
            "notes":         "",
        })

    logger.info(f"Jobspresso: {len(jobs)} matching jobs")
    return jobs
