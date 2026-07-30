"""
Workday ATS Scraper
Uses Workday's public jobs search API (POST).
Each company has its own Workday tenant — no auth needed for public jobs.
Filtering happens in pipeline/filter.py (unified discovery filter).
"""

import logging
from datetime import datetime

import requests

from models.job import JobRecord
from pipeline.legacy import filter_to_dicts

logger = logging.getLogger(__name__)

# Format: (tenant, wd_number, site_name)
WORKDAY_COMPANIES = [
    ("ibm", "5", "IBMJOBS"),
    ("cisco", "5", "External_Job_Board_To_Use"),
    ("oracle", "1", "Careers"),
    ("adobe", "5", "external_experienced"),
    ("qualcomm", "5", "External"),
    ("paypal", "1", "external"),
    ("nutanix", "1", "Nutanix"),
    ("purestorage", "1", "External"),
    ("zscaler", "1", "External"),
    ("commvault", "1", "CommvaultCareers"),
    ("wipro", "5", "External"),
    ("infosys", "1", "Infosys_External"),
    ("hcl", "1", "HCL"),
    ("ltimindtree", "1", "External"),
    ("mphasis", "1", "External"),
    ("vmware", "1", "VMware"),
    ("hashicorp", "1", "HashiCorp"),
    ("confluent", "1", "Confluent"),
    ("dbt-labs", "1", "dbt_Labs_Careers"),
    ("gitlab", "1", "GitLab"),
    ("splunk", "5", "External"),
    ("dynatrace", "1", "Dynatrace"),
    ("rapid7", "1", "External"),
    ("crowdstrike", "1", "External"),
    ("paloalto", "1", "external"),
]


def _scrape_company(tenant: str, wd_n: str, site: str) -> list[JobRecord]:
    today = datetime.now().strftime("%Y-%m-%d")
    jobs: list[JobRecord] = []

    url = f"https://{tenant}.wd{wd_n}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"
    headers = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
    payload = {
        "appliedFacets": {},
        "limit": 20,
        "offset": 0,
        "searchText": "site reliability engineer",
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        if resp.status_code != 200:
            logger.debug(f"Workday {tenant}: HTTP {resp.status_code}")
            return []

        for j in resp.json().get("jobPostings", []):
            title = j.get("title", "")
            location = j.get("locationsText", "") or j.get("primaryLocation", "")
            ext_url = j.get("externalPath", "")
            job_id = j.get("bulletFields", [""])[0] if j.get("bulletFields") else ext_url
            full_url = f"https://{tenant}.wd{wd_n}.myworkdayjobs.com/{site}{ext_url}" if ext_url else ""

            jobs.append(
                JobRecord(
                    url=full_url,
                    source="Workday",
                    company=tenant.replace("-", " ").title(),
                    title=title,
                    location=location or "India / Remote",
                    job_id=job_id or ext_url,
                    department=j.get("jobFamilyGroup", ""),
                    discovered_at=today,
                    notes=f"Workday — Apply at {full_url}" if full_url else "Workday — Apply via company site",
                )
            )
    except Exception as e:
        logger.debug(f"Workday {tenant} error: {e}")

    return jobs


def fetch_workday_raw() -> list[JobRecord]:
    all_jobs: list[JobRecord] = []
    for tenant, wd_n, site in WORKDAY_COMPANIES:
        all_jobs.extend(_scrape_company(tenant, wd_n, site))
    return all_jobs


def scrape_workday() -> list:
    raw = fetch_workday_raw()
    filtered = filter_to_dicts(raw)
    by_tenant: dict[str, int] = {}
    for j in filtered:
        by_tenant[j.get("company", "?")] = by_tenant.get(j.get("company", "?"), 0) + 1
    for tenant, count in by_tenant.items():
        logger.info(f"Workday {tenant}: {count} matches")
    return filtered
