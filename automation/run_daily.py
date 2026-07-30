#!/usr/bin/env python3
"""
shortlistr Daily Runner — legacy discovery / scoring helper.

Discovers roles, scores fit, and queues them for human review.
Never auto-submits applications (no Easy Apply / Naukri Apply / email send).

Usage:
    python run_daily.py            # Discover + queue for review
    python run_daily.py --dry-run  # Preview only
    python run_daily.py --test     # Limit to 1 job
"""

import sys, os, logging, json, argparse, time, inspect
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

from config import (
    LOG_DIR, DATA_DIR, CANDIDATE, PIPELINE_PATH, MIN_FIT_SCORE,
    DISABLED_LEGACY_SOURCES, LINKEDIN_SOURCE_CONFIG,
)
from portals_config import portals_summary, get_greenhouse_slugs, get_lever_slugs, get_ashby_slugs
from orchestrator.discovery import discover_and_filter, persist_discovered
from pipeline.filter import apply_fit_filter
from store import db as store
from store.pipeline_feed import feed_from_dicts
from observability.metrics import trace_span
# ── Legacy scrapers (opt-in) ─────────────────────────────────────────────────
from scrapers.naukri_scraper          import scrape_naukri
from scrapers.workday_scraper         import scrape_workday
from scrapers.smartrecruiters_scraper import scrape_smartrecruiters
from scrapers.wellfound_scraper       import scrape_wellfound
from scrapers.icims_scraper           import scrape_icims
from scrapers.linkedin_scraper        import scrape_linkedin
from scrapers.weworkremotely_scraper  import scrape_weworkremotely
from scrapers.workingnomads_scraper   import scrape_workingnomads
from scrapers.nodesk_scraper          import scrape_nodesk
from scrapers.jobspresso_scraper      import scrape_jobspresso
from scrapers.monster_scraper         import scrape_monster
from scrapers.careerbuilder_scraper   import scrape_careerbuilder
# ── Processors ───────────────────────────────────────────────────────────────
from processors.cover_letter          import generate_cover_letter, generate_subject
from processors.tracker               import load_existing_ids, append_jobs, update_job_status
from processors.job_filter            import filter_jobs, score_job
from processors.email_monitor         import process_recruiter_messages
from processors.apply_queue           import add_to_queue

# Legacy scrapers (opt-in via profile sources.legacy_enabled)
# ── Logging ───────────────────────────────────────────────────────────────────
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

log_file = os.path.join(LOG_DIR, f"run_{datetime.now().strftime('%Y%m%d')}.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

RESUME_PATH      = CANDIDATE["resume_path"]
MAX_EMAILS_PER_RUN = 10
FIT_SCORE_MIN    = MIN_FIT_SCORE


def _call_scraper(fn, log_totals: bool = False):
    """Invoke scraper; pass log_totals when supported."""
    params = inspect.signature(fn).parameters
    if log_totals and "log_totals" in params:
        return fn(log_totals=True)
    return fn()


def deduplicate(jobs, seen_ids):
    new_jobs, batch_ids = [], set()
    for job in jobs:
        key = str(job.get("job_id", "")) or job.get("url", "")
        if key and (key in seen_ids or key in batch_ids):
            continue
        new_jobs.append(job)
        if key:
            batch_ids.add(key)
    return new_jobs


def should_email(job):
    """Only email ATS jobs (Greenhouse/Lever/Ashby etc.) that have a company email."""
    return bool(job.get("company_email")) and job.get("source") not in ("Naukri", "LinkedIn")


def _feed_pipeline(fit_jobs: list, dry_run: bool = False):
    """Write strong-fit jobs to SQLite pipeline (exports pipeline.md for inbox)."""
    if not fit_jobs:
        return
    n = feed_from_dicts(fit_jobs, dry_run=dry_run, export_markdown=not dry_run)
    if dry_run:
        logger.info(f"DRY RUN — Would add {n} jobs to SQLite pipeline")
    elif n:
        logger.info(f"shortlistr pipeline: {n} strong-fit jobs → SQLite (+ pipeline.md export)")


def run(dry_run=False, test_mode=False, log_scrape_totals=False):
    logger.info("=" * 65)
    logger.info(f"shortlistr daily run | dry_run={dry_run} | test={test_mode}")
    logger.info(f"Candidate: {CANDIDATE['name']} | {CANDIDATE['email']}")
    logger.info(f"Resume: {RESUME_PATH}")
    logger.info(f"ATS sources: {portals_summary()}")
    logger.info(
        f"Company counts: GH={len(get_greenhouse_slugs())} "
        f"Lever={len(get_lever_slugs())} Ashby={len(get_ashby_slugs())}"
    )
    if log_scrape_totals:
        logger.info("Scrape totals mode: logging raw API counts vs filtered matches")
    logger.info("=" * 65)

    # ── Step 0: Recruiter inbox drafts (job alerts via gmail source adapter) ─
    logger.info("── Email Monitor (recruiter drafts) ──")
    try:
        n_drafts = process_recruiter_messages()
        logger.info(f"   Recruiter drafts saved: {n_drafts}")
    except Exception as e:
        logger.error(f"   Email monitor failed: {e}")

    seen_ids = load_existing_ids()
    logger.info(f"Loaded {len(seen_ids)} previously seen job IDs")

    run_id = store.start_run(dry_run=dry_run)
    all_raw = []
    source_stats: dict = {}

    # ── Core discovery via source registry ────────────────────────────────────
    logger.info("── Core discovery (source registry) ──")
    with trace_span("discover_all"):
        try:
            passed, rejected_disc, source_stats = discover_and_filter(
                log_totals=log_scrape_totals
            )
            all_raw.extend(j.to_dict() for j in passed)
            logger.info(
                f"   Registry: {len(passed)} passed discovery filter, "
                f"{len(rejected_disc)} rejected"
            )
            if not dry_run:
                persist_discovered(passed, run_id)
        except Exception as e:
            logger.error(f"   Core discovery failed: {e}")
            source_stats = {"error": str(e)}

    # ── Legacy sources (disabled by default) ──────────────────────────────────
    _legacy_map = {
        "workday": ("Workday", scrape_workday),
        "smartrecruiters": ("SmartRecruiters", scrape_smartrecruiters),
        "wellfound": ("Wellfound", scrape_wellfound),
        "icims": ("iCIMS", scrape_icims),
        "weworkremotely": ("WeWorkRemotely", scrape_weworkremotely),
        "workingnomads": ("WorkingNomads", scrape_workingnomads),
        "nodesk": ("NoDesk", scrape_nodesk),
        "jobspresso": ("Jobspresso", scrape_jobspresso),
        "monster": ("Monster", scrape_monster),
        "careerbuilder": ("CareerBuilder", scrape_careerbuilder),
    }
    for key, (label, fn) in _legacy_map.items():
        if key in DISABLED_LEGACY_SOURCES:
            continue
        logger.info(f"── Legacy scraping {label} ──")
        try:
            jobs = _call_scraper(fn, log_scrape_totals)
            logger.info(f"   {label}: {len(jobs)} matches")
            all_raw.extend(jobs)
        except Exception as e:
            logger.error(f"   {label} failed: {e}")

    # ── Naukri (API scrape only) ──────────────────────────────────────────────
    logger.info("── Scraping Naukri (WFH/Remote) ──")
    nk_raw = []
    try:
        nk_raw = scrape_naukri()
        logger.info(f"   Naukri scraped: {len(nk_raw)} raw matches")
    except Exception as e:
        logger.error(f"   Naukri scrape failed: {e}")

    # ── LinkedIn (opt-in; scrape only — never auto-submit) ────────────────────
    li_jobs = []
    if LINKEDIN_SOURCE_CONFIG.get("enabled"):
        logger.info("── LinkedIn (opt-in, scrape only) ──")
        try:
            li_jobs = scrape_linkedin(dry_run=True)
            logger.info(f"   LinkedIn: {len(li_jobs)} jobs")
            all_raw.extend(li_jobs)
        except Exception as e:
            logger.error(f"   LinkedIn scraper failed: {e}")
    else:
        logger.info("── LinkedIn skipped (sources.linkedin.enabled=false) ──")

    all_raw.extend(nk_raw)

    logger.info(f"\nTotal raw matches (all sources): {len(all_raw)}")

    # ── Deduplicate ───────────────────────────────────────────────────────────
    new_jobs = deduplicate(all_raw, seen_ids)
    logger.info(f"New (not seen before): {len(new_jobs)}")

    if test_mode and new_jobs:
        logger.info("TEST MODE: limiting to 1 job")
        new_jobs = new_jobs[:1]

    if not new_jobs:
        logger.info("No new jobs today. Saving empty handoff for morning review.")
        store.finish_run(
            run_id,
            source_stats=source_stats,
            discovered=len(all_raw),
            passed=len(all_raw),
            strong_fit=0,
        )
        if not dry_run:
            handoff = {"date": datetime.now().strftime("%Y-%m-%d"), "emails_sent": 0, "linkedin_easy_applied": 0, "linkedin_manual": []}
            with open(os.path.join(DATA_DIR, "linkedin_handoff.json"), "w") as f:
                json.dump(handoff, f, indent=2)
        return

    # ── Relevance / Fit Scoring ───────────────────────────────────────────────
    logger.info(f"\n── Relevance filtering (min_score={FIT_SCORE_MIN}) ──")
    fit_jobs, skipped_jobs = filter_jobs(new_jobs, min_score=FIT_SCORE_MIN)

    logger.info(f"Strong fit: {len(fit_jobs)} | Skipped (weak fit): {len(skipped_jobs)}")
    for j in skipped_jobs[:10]:
        logger.info(f"  SKIP [{j.get('fit_score',0):2d}] {j.get('company','')} — {j.get('title','')} | {j.get('fit_reason','')}")

    if not fit_jobs:
        logger.info("No strong-fit jobs today. Saving empty handoff for morning review.")
        store.finish_run(
            run_id,
            source_stats=source_stats,
            discovered=len(all_raw),
            passed=len(new_jobs) if new_jobs else 0,
            strong_fit=0,
        )
        if not dry_run:
            handoff = {"date": datetime.now().strftime("%Y-%m-%d"), "emails_sent": 0, "linkedin_easy_applied": 0, "linkedin_manual": []}
            with open(os.path.join(DATA_DIR, "linkedin_handoff.json"), "w") as f:
                json.dump(handoff, f, indent=2)
        return

    # ── Save ALL new jobs to tracker (fit + skipped, status reflects fit) ─────
    for j in skipped_jobs:
        j["status"] = "Skipped (weak fit)"
        j["notes"]  = j.get("fit_reason", "Low relevance")
    added = append_jobs(fit_jobs + skipped_jobs)
    logger.info(f"Added {added} new rows to tracker")

    # ── Queue for human review (never auto-email / auto-submit) ───────────────
    emails_sent  = 0
    applied_jobs = []
    linkedin_manual = []
    queued = 0

    for job in fit_jobs:
        src = job.get("source", "")
        if src == "LinkedIn":
            linkedin_manual.append(job)
            logger.info(
                f"  LinkedIn [{job.get('fit_score',0):2d}] queue: "
                f"{job.get('company','')} — {job.get('title','')}"
            )
        elif not should_email(job):
            logger.info(f"  Platform apply [{src}]: {job.get('company','')} — {job.get('title','')}")
        else:
            # Generate materials but do not send — user reviews and submits.
            cover_letter = generate_cover_letter(job)
            subject      = cover_letter.get("subject") or generate_subject(job)
            _ = subject  # materials available on job via generate_cover_letter side effects / logs
            body         = cover_letter.get("body", cover_letter) if isinstance(cover_letter, dict) else cover_letter
            _ = body
            to_email     = job.get("company_email") or ""
            logger.info(
                f"  Prep [{job.get('fit_score',0):2d}] {job['company']} — "
                f"{job['title']} → {to_email or '(no email)'}"
                f"{' (dry-run)' if dry_run else ''}"
            )
            if not dry_run:
                job["notes"] = f"Cover letter ready; review before sending to {to_email}"
            queued += 1

    # Naukri / LinkedIn: discover only — never click Apply/Submit
    logger.info("── Auto-submit disabled (open-source ethics) ──")
    nk_fit, nk_skip = filter_jobs(nk_raw, min_score=FIT_SCORE_MIN)
    logger.info(f"   Naukri fit: {len(nk_fit)} | skipped: {len(nk_skip)} (queued for review, not applied)")

    logger.info("\n" + "=" * 65)
    logger.info(f"Emails sent:               {emails_sent} (auto-send disabled)")
    logger.info(f"Cover letters prepared:    {queued}")
    logger.info(f"LinkedIn Manual Apply:     {len(linkedin_manual)} (strong fit, apply yourself)")
    logger.info(f"Naukri strong-fit:         {len(nk_fit)} (apply yourself)")
    logger.info(f"Auto-submitted today:      0")
    logger.info("=" * 65)

    # Log LinkedIn manual apply list so you can act on them
    if linkedin_manual:
        logger.info("\n── LinkedIn Strong-Fit Jobs for Manual Apply ──")
        for j in sorted(linkedin_manual, key=lambda x: -x.get("fit_score", 0)):
            logger.info(f"  [{j.get('fit_score',0):2d}] {j.get('company',''):25} {j.get('title','')[:40]:40} → {j.get('url','')}")

    # ── Save JSON snapshot ────────────────────────────────────────────────────
    json_path = os.path.join(DATA_DIR, f"jobs_{datetime.now().strftime('%Y%m%d')}.json")
    with open(json_path, "w") as f:
        json.dump(fit_jobs, f, indent=2)

    # ── Feed strong-fit jobs into shortlistr pipeline.md ─────────────────────
    _feed_pipeline(fit_jobs, dry_run=dry_run)

    # ── Add to apply queue (morning review — no auto-submit) ─────────────────
    # Jobs from non-ATS sources (no company_email) go into the queue for
    # your manual review each morning. Run:
    #   python3 processors/apply_queue.py --status    → see queue
    #   python3 processors/apply_queue.py --submit    → submit your YES decisions
    non_ats_fit = [j for j in fit_jobs if not j.get("company_email")]
    if non_ats_fit and not dry_run:
        add_to_queue(non_ats_fit)
        logger.info(
            f"Apply queue: {len(non_ats_fit)} jobs added for morning review → "
            f"{os.path.join(DATA_DIR, 'apply_queue.md')}"
        )
    elif dry_run:
        logger.info(f"DRY RUN — Would add {len(non_ats_fit)} jobs to apply queue")

    # ── Save LinkedIn manual-apply jobs for morning review ───────────────
    # No email sent here. Review via /shortlistr inbox (or apply_queue.py) when
    # you are ready — there is no separate scheduled evaluator cron job.
    if not dry_run:
        handoff = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "emails_sent": emails_sent,
            "linkedin_easy_applied": 0,
            "linkedin_manual": linkedin_manual,
        }
        handoff_path = os.path.join(DATA_DIR, "linkedin_handoff.json")
        with open(handoff_path, "w") as f:
            json.dump(handoff, f, indent=2)
        logger.info(f"Saved {len(linkedin_manual)} LinkedIn manual jobs to linkedin_handoff.json for morning review")
    else:
        logger.info(f"DRY RUN — Would save {len(linkedin_manual)} LinkedIn jobs to handoff file")
        logger.info("DRY RUN — Review later via /shortlistr inbox or apply_queue.py")

    # macOS notification
    try:
        os.system(
            f'osascript -e \'display notification '
            f'"{len(fit_jobs)} fit jobs | 0 auto-submitted" '
            f'with title "shortlistr" sound name "Glass"\''
        )
    except Exception:
        pass

    store.finish_run(
        run_id,
        source_stats=source_stats,
        discovered=len(all_raw),
        passed=len(new_jobs),
        strong_fit=len(fit_jobs),
    )

    logger.info("DONE.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--test",    action="store_true")
    parser.add_argument(
        "--log-scrape-totals",
        action="store_true",
        help="Log raw API job counts vs title/location filtered counts per source",
    )
    args = parser.parse_args()
    run(dry_run=args.dry_run, test_mode=args.test, log_scrape_totals=args.log_scrape_totals)
