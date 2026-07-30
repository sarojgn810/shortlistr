"""
SmartRecruiters ATS Scraper — public API, no auth required.
Filtering happens in pipeline/filter.py (unified discovery filter).
"""

import logging
from datetime import datetime

import requests

from models.job import JobRecord
from pipeline.legacy import filter_to_dicts

logger = logging.getLogger(__name__)

SMARTRECRUITERS_COMPANIES = [
    "visa", "linkedin", "informatica", "bosch", "ericsson",
    "nokia", "siemens", "philips", "sap-se", "ntt-data",
    "klarna", "adyen", "checkout-com", "rapyd", "nium",
    "stripe", "braintree", "worldline",
    "deutsche-bank", "jpmorgan", "barclays", "ubs", "credit-suisse",
    "societe-generale", "bnpparibas",
    "twilio", "sendgrid", "vonage", "messagebird", "bandwidth",
    "zendesk", "freshservice", "servicenow",
]


def fetch_smartrecruiters_raw() -> list[JobRecord]:
    today = datetime.now().strftime("%Y-%m-%d")
    all_jobs: list[JobRecord] = []

    for slug in SMARTRECRUITERS_COMPANIES:
        try:
            url = f"https://api.smartrecruiters.com/v1/companies/{slug}/postings"
            resp = requests.get(url, params={"status": "PUBLIC", "limit": 100}, timeout=12)
            if resp.status_code != 200:
                logger.debug(f"SmartRecruiters {slug}: HTTP {resp.status_code}")
                continue

            for j in resp.json().get("content", []):
                title = j.get("name", "")
                loc = j.get("location") or {}
                location = f"{loc.get('city', '')}, {loc.get('country', '')}".strip(", ")
                job_id = j.get("id", "")
                job_url = f"https://jobs.smartrecruiters.com/{slug}/{job_id}"

                all_jobs.append(
                    JobRecord(
                        url=job_url,
                        source="SmartRecruiters",
                        company=j.get("company", {}).get("name", slug.title()),
                        title=title,
                        location=location or "Remote / India",
                        job_id=job_id,
                        department=j.get("department", {}).get("label", ""),
                        discovered_at=today,
                        notes="SmartRecruiters — Apply via company site",
                    )
                )
        except Exception as e:
            logger.debug(f"SmartRecruiters {slug} error: {e}")

    return all_jobs


def scrape_smartrecruiters() -> list:
    raw = fetch_smartrecruiters_raw()
    filtered = filter_to_dicts(raw)
    by_slug: dict[str, int] = {}
    for j in filtered:
        co = j.get("company", "?")
        by_slug[co] = by_slug.get(co, 0) + 1
    for slug, count in by_slug.items():
        if count:
            logger.info(f"SmartRecruiters {slug}: {count} matches")
    return filtered
