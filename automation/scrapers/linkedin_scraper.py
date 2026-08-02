"""
LinkedIn job discovery (opt-in scrape).

Does NOT auto-submit applications. Prefill / apply happens only via the
dashboard apply-assist path, where the user always clicks Submit.
"""

import os, time, random, logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

from config import LINKEDIN_CONFIG
from portals_config import get_tracked_company_names

LINKEDIN_EMAIL    = LINKEDIN_CONFIG["email"]
LINKEDIN_PASSWORD = LINKEDIN_CONFIG["password"]

BASE_DIR     = Path(__file__).parent.parent
SESSION_DIR  = BASE_DIR / ".browser_sessions" / "linkedin"

# Field-neutral defaults — discovery filter / profile titles refine further.
SEARCH_QUERIES = [
    "Software Engineer",
    "Data Analyst",
    "Product Manager",
    "Business Analyst",
    "Project Manager",
]

# Soft title hints — empty means keep all titles from the scrape cards.
# Prefer profile targeting + pipeline filter over scraper-side role bias.
TITLE_MUST_CONTAIN = [
    "engineer", "analyst", "manager", "developer", "designer",
    "scientist", "architect", "specialist", "lead", "director",
]

# Noise filter — skip obvious non-matches (keep field-neutral)
TITLE_BLACKLIST = [
    "sales", "account executive", "marketing", "recruiter", "hr ",
    "helpdesk", "desktop support", "it support",
    "junior", "intern", "trainee",
]

MAX_JOBS_PER_QUERY = 15


def _sleep(mn=1.5, mx=3.5):
    time.sleep(random.uniform(mn, mx))


def _title_ok(title: str) -> bool:
    t = title.lower()
    has_kw   = any(kw in t for kw in TITLE_MUST_CONTAIN)
    no_noise = not any(bl in t for bl in TITLE_BLACKLIST)
    return has_kw and no_noise


def _is_logged_in(page) -> bool:
    return "feed" in page.url or "jobs" in page.url or page.query_selector("div.global-nav") is not None


def _login(page) -> bool:
    if not LINKEDIN_PASSWORD:
        logger.error("LINKEDIN_PASSWORD env var not set.")
        return False
    logger.info("LinkedIn: logging in...")
    page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")
    _sleep()
    page.fill("#username", LINKEDIN_EMAIL)
    page.fill("#password", LINKEDIN_PASSWORD)
    _sleep(0.5, 1.5)
    page.click('button[type="submit"]')
    page.wait_for_timeout(4000)
    if "checkpoint" in page.url or "challenge" in page.url:
        logger.warning("LinkedIn: 2FA/CAPTCHA required. Complete manually then re-run.")
        return False
    return _is_logged_in(page)


def _search_jobs(page, query: str) -> list:
    jobs = []
    encoded = query.replace(" ", "%20")
    # f_WT=2 = Remote, f_TPR=r86400 = past 24h, f_E=4 = Senior level
    url = (
        f"https://www.linkedin.com/jobs/search/?keywords={encoded}"
        f"&location=India&f_WT=2&f_TPR=r86400&sortBy=DD"
    )
    page.goto(url, wait_until="domcontentloaded")
    _sleep(2, 4)

    for _ in range(3):
        page.evaluate("window.scrollBy(0, 800)")
        _sleep(1, 2)

    # Try both card selectors (LinkedIn changes their DOM)
    cards = page.query_selector_all("li.jobs-search-results__list-item")
    if not cards:
        cards = page.query_selector_all("div.job-search-card")

    logger.info(f"LinkedIn '{query}': {len(cards)} cards found")

    for card in cards[:MAX_JOBS_PER_QUERY]:
        try:
            title_el = (
                card.query_selector("a.job-card-list__title") or
                card.query_selector("h3.base-search-card__title") or
                card.query_selector("span.sr-only")
            )
            company_el = (
                card.query_selector("span.job-card-container__company-name") or
                card.query_selector("h4.base-search-card__subtitle")
            )
            location_el = (
                card.query_selector("li.job-card-container__metadata-item") or
                card.query_selector("span.job-search-card__location")
            )
            link_el = (
                card.query_selector("a.job-card-list__title") or
                card.query_selector("a.base-card__full-link")
            )

            title    = title_el.inner_text().strip()    if title_el    else ""
            company  = company_el.inner_text().strip()  if company_el  else ""
            location = location_el.inner_text().strip() if location_el else ""
            url      = link_el.get_attribute("href")    if link_el     else ""
            if url and not url.startswith("http"):
                url = "https://www.linkedin.com" + url

            if not title or not _title_ok(title):
                continue

            # Detect Easy Apply — check multiple indicators
            card_html  = card.inner_html()
            easy_apply = (
                "Easy Apply" in card_html or
                "easy-apply" in card_html.lower() or
                card.query_selector("[class*='easy-apply']") is not None
            )

            job_id = ""
            if "/jobs/view/" in (url or ""):
                job_id = url.split("/jobs/view/")[1].split("/")[0].split("?")[0]
            elif "currentJobId=" in (url or ""):
                job_id = url.split("currentJobId=")[1].split("&")[0]

            jobs.append({
                "title":      title,
                "company":    company,
                "location":   location,
                "url":        url.split("?")[0] if url else "",
                "easy_apply": easy_apply,
                "job_id":     job_id,
                "source":     "LinkedIn",
            })
        except Exception as e:
            logger.debug(f"Card parse error: {e}")

    return jobs


def _search_company_targeted(page, company: str) -> list:
    """Search LinkedIn for roles at a specific company (scrape only).
    Uses ONE combined query. Returns only jobs where the company name
    actually matches the card's company field.
    """
    query = f"Software Engineer {company}"
    found = _search_jobs(page, query)
    if not found:
        return []

    co_key_words = [w for w in company.lower()
                    .replace("&", "").replace(",", "").replace(".", "").split()
                    if len(w) > 3]
    if not co_key_words:
        return []

    jobs, seen = [], set()
    for j in found:
        co = j.get("company", "").lower()
        if not any(w in co for w in co_key_words):
            continue   # card is from a different company (keyword match only)
        uid = j.get("job_id") or j.get("url", "")
        if uid in seen:
            continue
        seen.add(uid)
        jobs.append(j)
    return jobs


def scrape_linkedin(dry_run: bool = False) -> list:
    """Discover LinkedIn jobs. Never submits applications (dry_run ignored)."""
    _ = dry_run  # kept for call-site compatibility
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.error("Install Playwright from Connections in the dashboard.")
        return []

    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    all_jobs = []

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=str(SESSION_DIR),
            headless=True,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = browser.pages[0] if browser.pages else browser.new_page()

        page.goto("https://www.linkedin.com/jobs", wait_until="domcontentloaded")
        _sleep(2, 3)
        if not _is_logged_in(page):
            if not _login(page):
                browser.close()
                return []

        seen_ids = set()

        def _add_unique(jobs_list, new_jobs):
            for j in new_jobs:
                uid = j.get("job_id") or j.get("url", "")
                if uid and uid not in seen_ids:
                    seen_ids.add(uid)
                    jobs_list.append(j)

        raw_from_queries = []
        for query in SEARCH_QUERIES:
            _add_unique(raw_from_queries, _search_jobs(page, query))

        target_companies = get_tracked_company_names()
        logger.info(f"LinkedIn: company-targeted pass ({len(target_companies)} companies)...")
        for company in target_companies:
            try:
                cjobs = _search_company_targeted(page, company)
                if cjobs:
                    logger.info(f"   {company}: {len(cjobs)} matches")
                _add_unique(raw_from_queries, cjobs)
                _sleep(0.5, 1.0)
            except Exception as e:
                logger.debug(f"   {company} search failed: {e}")

        logger.info(f"LinkedIn: {len(raw_from_queries)} unique jobs after dedup")

        for job in raw_from_queries:
            job.update({
                "date_found":    today,
                "department":    "",
                "jd_snippet":    "",
                "company_email": "",
                "status":        "New",
                "email_sent":    "No",
                "notes":         (
                    "LinkedIn (Easy Apply available — apply yourself)"
                    if job.get("easy_apply")
                    else "LinkedIn — apply via platform"
                ),
            })
            all_jobs.append(job)

        browser.close()

    logger.info(f"LinkedIn: {len(all_jobs)} jobs discovered (scrape only; never auto-submit)")
    return all_jobs


# Back-compat alias — callers must not expect submit behavior.
scrape_and_apply_linkedin = scrape_linkedin
