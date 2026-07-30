"""
We Work Remotely Scraper — RSS feeds (no auth needed).
Feeds: https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss
"""

import requests
import logging
import xml.etree.ElementTree as ET
from datetime import datetime
from config import SEARCH_KEYWORDS

logger = logging.getLogger(__name__)

FEEDS = [
    "https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss",
    "https://weworkremotely.com/categories/remote-back-end-programming-jobs.rss",
    "https://weworkremotely.com/categories/remote-full-stack-programming-jobs.rss",
]

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; shortlistr-bot/1.0)"}

def scrape_weworkremotely() -> list[dict]:
    jobs = []
    today = datetime.now().strftime("%Y-%m-%d")
    seen = set()

    for feed_url in FEEDS:
        try:
            resp = requests.get(feed_url, headers=HEADERS, timeout=15)
            if resp.status_code != 200:
                logger.warning(f"WWR feed {feed_url}: HTTP {resp.status_code}")
                continue
            root = ET.fromstring(resp.content)
        except Exception as e:
            logger.warning(f"WWR feed error: {e}")
            continue

        for item in root.findall(".//item"):
            raw_title = (item.findtext("title") or "").strip()
            # WWR format: "Company: Job Title"
            if ": " in raw_title:
                company, title = raw_title.split(": ", 1)
            else:
                company, title = "", raw_title

            if not any(kw in title.lower() for kw in SEARCH_KEYWORDS):
                continue

            link = (item.findtext("link") or "").strip()
            guid = item.findtext("guid") or link
            if guid in seen:
                continue
            seen.add(guid)

            region = (item.findtext("{https://weworkremotely.com}region") or "Worldwide").strip()

            jobs.append({
                "date_found":    today,
                "source":        "WeWorkRemotely",
                "company":       company.strip(),
                "title":         title.strip(),
                "location":      region or "Remote",
                "url":           link,
                "job_id":        guid,
                "department":    "",
                "jd_snippet":    (item.findtext("description") or "")[:800].strip(),
                "salary":        "",
                "company_email": "",
                "status":        "New",
                "email_sent":    "No",
                "notes":         "",
            })

    logger.info(f"WeWorkRemotely: {len(jobs)} matching jobs")
    return jobs
