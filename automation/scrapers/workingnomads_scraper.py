"""
Working Nomads Scraper — JSON API (no auth needed).
API: https://www.workingnomads.com/api/exposed_jobs/?category=devops
"""

import requests
import logging
from datetime import datetime
from config import SEARCH_KEYWORDS

logger = logging.getLogger(__name__)

CATEGORIES = ["devops", "sysadmin", "backend"]
API_BASE = "https://www.workingnomads.com/api/exposed_jobs/"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; shortlistr-bot/1.0)"}

def scrape_workingnomads() -> list[dict]:
    jobs = []
    today = datetime.now().strftime("%Y-%m-%d")
    seen = set()

    for cat in CATEGORIES:
        try:
            resp = requests.get(API_BASE, params={"category": cat}, headers=HEADERS, timeout=15)
            if resp.status_code != 200:
                logger.warning(f"WorkingNomads {cat}: HTTP {resp.status_code}")
                continue
            data = resp.json()
        except Exception as e:
            logger.warning(f"WorkingNomads {cat} error: {e}")
            continue

        for job in data:
            title = job.get("title", "")
            if not any(kw in title.lower() for kw in SEARCH_KEYWORDS):
                continue
            job_id = str(job.get("id", ""))
            if job_id in seen:
                continue
            seen.add(job_id)

            jobs.append({
                "date_found":    today,
                "source":        "WorkingNomads",
                "company":       job.get("company", ""),
                "title":         title,
                "location":      "Remote",
                "url":           job.get("url", ""),
                "job_id":        job_id,
                "department":    cat,
                "jd_snippet":    (job.get("description", "") or "")[:800].strip(),
                "salary":        job.get("salary", ""),
                "company_email": "",
                "status":        "New",
                "email_sent":    "No",
                "notes":         "",
            })

    logger.info(f"WorkingNomads: {len(jobs)} matching jobs")
    return jobs
