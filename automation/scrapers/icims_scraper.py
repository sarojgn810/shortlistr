"""
iCIMS ATS Scraper — public job feeds.
Filtering happens in pipeline/filter.py (unified discovery filter).
"""

import logging
import re
from datetime import datetime

import requests

from models.job import JobRecord
from pipeline.legacy import filter_to_dicts

logger = logging.getLogger(__name__)

ICIMS_COMPANIES = [
    ("Capgemini", "careers-capgemini"),
    ("Cognizant", "careers-cognizant"),
    ("Accenture", "accenture"),
    ("DXC Technology", "careers-dxc"),
    ("Tech Mahindra", "careers-techmahindra"),
    ("Hexaware", "careers-hexaware"),
    ("Zensar", "careers-zensar"),
    ("Persistent", "careers-persistent"),
    ("Mindtree", "careers-mindtree"),
    ("Mphasis", "careers-mphasis"),
    ("Kyndryl", "careers-kyndryl"),
    ("NTT Data", "careers-nttdata"),
    ("UST Global", "careers-ust"),
    ("Mastech Digital", "careers-mastech"),
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/json, text/javascript, */*",
}


def _scrape_company(company_name: str, subdomain: str) -> list[JobRecord]:
    today = datetime.now().strftime("%Y-%m-%d")
    jobs: list[JobRecord] = []
    seen: set[str] = set()

    for kw in ["site reliability engineer", "devops", "platform engineer", "cloud engineer"]:
        try:
            url = f"https://{subdomain}.icims.com/jobs/search"
            params = {
                "ss": "1",
                "searchKeyword": kw,
                "searchLocation": "India",
                "in_iframe": "1",
            }
            resp = requests.get(url, params=params, headers=HEADERS, timeout=12)
            if resp.status_code != 200:
                continue

            for path, job_id, title in re.findall(
                r'href="(/jobs/(\d+)/[^"]+)"[^>]*>([^<]+)</a>', resp.text
            ):
                title = title.strip()
                if not title or job_id in seen:
                    continue
                seen.add(job_id)
                job_url = f"https://{subdomain}.icims.com{path}"
                jobs.append(
                    JobRecord(
                        url=job_url,
                        source="iCIMS",
                        company=company_name,
                        title=title,
                        location="India / Remote",
                        job_id=job_id,
                        discovered_at=today,
                        notes="iCIMS — Apply via company site",
                    )
                )
        except Exception as e:
            logger.debug(f"iCIMS {company_name} error: {e}")

    return jobs


def fetch_icims_raw() -> list[JobRecord]:
    all_jobs: list[JobRecord] = []
    for company_name, subdomain in ICIMS_COMPANIES:
        all_jobs.extend(_scrape_company(company_name, subdomain))
    return all_jobs


def scrape_icims() -> list:
    raw = fetch_icims_raw()
    filtered = filter_to_dicts(raw)
    by_co: dict[str, int] = {}
    for j in filtered:
        co = j.get("company", "?")
        by_co[co] = by_co.get(co, 0) + 1
    for company, count in by_co.items():
        if count:
            logger.info(f"iCIMS {company}: {count} matches")
    return filtered
