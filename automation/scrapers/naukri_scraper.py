"""
Naukri job discovery (API scrape).

Does NOT auto-submit applications. Use dashboard apply-assist for prefill;
you always click Submit yourself.
"""

import requests
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

_REMOTE_TERMS = {"remote", "anywhere", "worldwide", "global", "work from home", "wfh"}


def _build_search_pairs() -> list[tuple[str, str]]:
    """Build (title, location) pairs from profile config."""
    import config as _cfg
    titles = _cfg.search_titles(5)
    locs = _cfg.search_locations(3)
    if not locs:
        locs = ["work from home"]
    pairs = []
    for title in titles:
        for loc in locs[:3]:
            pairs.append((title, loc))
    return pairs[:15]


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": "https://www.naukri.com/",
    "appid": "109",
    "systemid": "109",
}


# ── Part 1: Scrape job listings ────────────────────────────────────────────────

def _placeholder_labels(listing: dict) -> dict[str, str]:
    """Naukri packs experience/salary/location into typed placeholders."""
    out: dict[str, str] = {}
    for p in listing.get("placeholders") or []:
        if not isinstance(p, dict):
            continue
        ptype = str(p.get("type") or "").strip().lower()
        label = str(p.get("label") or "").strip()
        if ptype and label:
            out[ptype] = label
    return out


def _skills_from_listing(listing: dict) -> list[str]:
    raw = listing.get("tagsAndSkills") or listing.get("keySkills") or ""
    if isinstance(raw, str):
        parts = [s.strip() for s in raw.replace("|", ",").split(",") if s.strip()]
        return parts[:40]
    if isinstance(raw, list):
        out: list[str] = []
        for item in raw:
            if isinstance(item, dict):
                skill = str(item.get("skill") or item.get("label") or "").strip()
            else:
                skill = str(item or "").strip()
            if skill:
                out.append(skill)
        return out[:40]
    return []


def _parse_naukri_listing(j: dict) -> dict:
    """Normalize one Naukri jobDetails row into the legacy job dict shape.

    Salary, experience and skills used to be dropped on the floor — they are
    what made Naukri the richest India source in the Apify inventory run, and
    they belong on the JobRecord (salary column + metadata) so scoring and
    the UI can use them without a second scrape.
    """
    job_id = str(j.get("jobId", "") or j.get("jobTitleSlug", ""))
    title = str(j.get("title", "") or "")
    company = str(j.get("companyName", "") or "")
    placeholders = _placeholder_labels(j)
    location = placeholders.get("location") or ""
    if not location and j.get("placeholders"):
        first = j["placeholders"][0] if isinstance(j["placeholders"][0], dict) else {}
        location = ", ".join(str(first.get("label", "")).split(",")[:2])
    url = j.get("jdURL", "") or (
        f"https://www.naukri.com/{j.get('jobTitleSlug', '')}-{job_id}" if job_id else ""
    )
    snippet = j.get("jobDescription", "")[:800] if j.get("jobDescription") else ""
    salary = placeholders.get("salary") or str(j.get("salaryDetail") or "").strip()
    if salary.lower() in ("not disclosed", "unpaid"):
        # Empty means unknown — keep "Not disclosed" out of the salary column.
        salary = ""
    experience = placeholders.get("experience") or str(j.get("experienceText") or "").strip()
    skills = _skills_from_listing(j)
    created = (
        j.get("createdDate")
        or j.get("footerPlaceholderLabel")
        or j.get("postedDate")
        or ""
    )
    return {
        "date_found": "",
        "source": "Naukri",
        "company": company,
        "title": title,
        "location": location or "Work From Home",
        "url": url,
        "job_id": job_id,
        "department": "",
        "jd_snippet": snippet,
        "salary": salary,
        "company_email": "",
        "status": "New",
        "email_sent": "No",
        "notes": "Naukri",
        "metadata": {
            "skills": skills,
            "experience": experience,
            "posted_label": str(created),
            "source_job_id": job_id,
        },
    }


def scrape_naukri() -> list:
    """Scrape Naukri for jobs via search API. Returns job dicts."""
    today = datetime.now().strftime("%Y-%m-%d")
    jobs  = []
    seen  = set()

    for keyword, location in _build_search_pairs():
        try:
            params = {
                "noOfResults": 20,
                "urlType": "search_by_keyword",
                "searchType": "adv",
                "keyword": keyword,
                "location": location,
                "experience": "5",
                "k": keyword,
                "l": location,
                "sort": "1",             # relevance
            }
            if location.lower() in _REMOTE_TERMS:
                params["wfhType"] = "3"
            resp = requests.get(
                "https://www.naukri.com/jobapi/v3/search",
                params=params,
                headers=HEADERS,
                timeout=15,
            )
            if resp.status_code != 200:
                logger.debug(f"Naukri API {resp.status_code} for '{keyword}'")
                continue

            data     = resp.json()
            listings = data.get("jobDetails", [])

            for j in listings:
                job_id = str(j.get("jobId", "") or j.get("jobTitleSlug", ""))
                if job_id in seen:
                    continue
                seen.add(job_id)

                parsed = _parse_naukri_listing(j)
                if not parsed.get("url"):
                    continue
                parsed["date_found"] = today
                jobs.append(parsed)

            logger.info(f"Naukri '{keyword}': {len(listings)} results")

        except Exception as e:
            logger.warning(f"Naukri scrape error for '{keyword}': {e}")

    return jobs


def auto_apply_naukri(jobs: list, dry_run: bool = False) -> list:
    """Removed: never auto-submits. Kept as a no-op for legacy call sites."""
    _ = dry_run
    if jobs:
        logger.info(
            "Naukri auto-apply is disabled (open-source ethics). "
            "Queue roles in the dashboard and click Submit yourself."
        )
    return jobs
