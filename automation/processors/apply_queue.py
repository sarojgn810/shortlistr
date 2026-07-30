"""
shortlistr — Morning Review Queue

Run this after run_daily.py to review today's jobs and approve or skip each one.
Approved jobs automatically trigger CV PDF + interview prep generation.

Usage:
    python -m processors.apply_queue          # interactive review
    python -m processors.apply_queue --auto   # auto-approve all strong-fit (score >= 60)
"""

import os
import sys
import json
import logging
from datetime import datetime
from glob import glob

from config import DATA_DIR, OUTPUT_DIR, PREP_DIR

logger = logging.getLogger(__name__)

QUEUE_FILE  = os.path.join(DATA_DIR, "queue.json")


# ── Queue persistence ──────────────────────────────────────────────────────────

def _load_queue() -> dict:
    """Load saved queue decisions {job_id: 'approved'|'skipped'|'later'}."""
    if os.path.exists(QUEUE_FILE):
        try:
            with open(QUEUE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_queue(decisions: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(QUEUE_FILE, "w") as f:
        json.dump(decisions, f, indent=2)


# ── Load today's jobs ──────────────────────────────────────────────────────────

def _load_latest_jobs() -> list[dict]:
    """Load the most recent jobs JSON from data/."""
    pattern = os.path.join(DATA_DIR, "jobs_*.json")
    files   = sorted(glob(pattern), reverse=True)
    if not files:
        return []
    try:
        with open(files[0]) as f:
            jobs = json.load(f)
        logger.info(f"Loaded {len(jobs)} jobs from {os.path.basename(files[0])}")
        return jobs
    except Exception as e:
        logger.error(f"Could not load jobs: {e}")
        return []


def _pending_jobs(jobs: list[dict], decisions: dict) -> list[dict]:
    """Return jobs not yet decided, sorted by fit_score descending."""
    pending = [j for j in jobs if str(j.get("job_id", "")) not in decisions]
    return sorted(pending, key=lambda x: -x.get("fit_score", 0))


# ── Display ────────────────────────────────────────────────────────────────────

def _display_job(job: dict, idx: int, total: int):
    score    = job.get("fit_score", 0)
    score_bar = "█" * (score // 10) + "░" * (10 - score // 10)

    print(f"\n{'─'*65}")
    print(f"  [{idx}/{total}]  {job.get('company', '?')}  —  {job.get('title', '?')}")
    print(f"  Source   : {job.get('source', '?')}")
    print(f"  Location : {job.get('location', 'Not specified')}")
    print(f"  Score    : {score:3d}/100  {score_bar}")
    print(f"  Reason   : {job.get('fit_reason', '')}")
    if job.get("url"):
        print(f"  URL      : {job['url']}")
    if job.get("jd_snippet"):
        snippet = job["jd_snippet"][:220].replace("\n", " ")
        print(f"  JD       : {snippet}...")
    print(f"{'─'*65}")


# ── Post-approval generators ───────────────────────────────────────────────────

def _run_cv_generator(approved: list[dict]):
    try:
        from processors.generate_cv import generate_cv_batch
        results = generate_cv_batch(approved)
        for r in results:
            if r.get("success"):
                print(f"  ✓ CV PDF  → {r['path']}")
            else:
                print(f"  ✗ CV PDF failed: {r.get('error', '?')}")
    except Exception as e:
        logger.warning(f"CV generation skipped: {e}")


def _run_prep_generator(approved: list[dict]):
    try:
        from processors.generate_prep import generate_prep_batch
        results = generate_prep_batch(approved)
        for r in results:
            if r.get("success"):
                print(f"  ✓ Prep    → {r['path']}")
            else:
                print(f"  ✗ Prep failed: {r.get('error', '?')}")
    except Exception as e:
        logger.warning(f"Interview prep generation skipped: {e}")


def submit_approved(approved: list[dict]):
    """Called after interactive review. Runs CV + prep generators."""
    if not approved:
        print("\nNo jobs approved.")
        return

    print(f"\n{'═'*65}")
    print(f"  Generating assets for {len(approved)} approved job(s)...")
    print(f"{'═'*65}")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(PREP_DIR, exist_ok=True)

    _run_cv_generator(approved)
    _run_prep_generator(approved)
    _record_prep_receipts(approved)

    print(f"\n  Done. Check:")
    print(f"    output/        — CV PDFs")
    print(f"    interview-prep/ — prep guides")


def _record_prep_receipts(approved: list[dict]):
    """Write prep-channel receipts (assets generated, not yet submitted)."""
    try:
        from models.job import job_id_from_url
        from store import db as store
        from store.receipts import create_receipt
        from store.status import mark_approved

        store.init_db()
        for job in approved:
            url = job.get("url") or ""
            if not url:
                continue
            jid = job.get("job_id") or job_id_from_url(url)
            try:
                mark_approved(jid, actor="apply_queue")
            except Exception:
                pass
            create_receipt(
                jid,
                "prep",
                fields={
                    "company": job.get("company", ""),
                    "role": job.get("title", ""),
                    "fit_score": job.get("fit_score", 0),
                    "note": "CV and prep generated — not submitted",
                },
                resume_path=job.get("cv_path"),
                cover_letter_text=None,
                actor="apply_queue",
            )
    except Exception as e:
        logger.warning(f"Prep receipts skipped: {e}")


# ── Interactive review ─────────────────────────────────────────────────────────

def run_review(auto_approve_threshold: int = 0) -> list[dict]:
    """
    Interactive morning review.

    auto_approve_threshold: if > 0, auto-approve jobs scoring at or above this.
    Returns list of approved jobs.
    """
    jobs      = _load_latest_jobs()
    decisions = _load_queue()

    if not jobs:
        print("No jobs found. Run python run_daily.py first.")
        return []

    pending   = _pending_jobs(jobs, decisions)
    approved  = []

    if not pending:
        print("All jobs already reviewed. Nothing pending.")
        return []

    print(f"\n{'═'*65}")
    print(f"  SHORTLISTR — Morning Review Queue")
    print(f"  {len(pending)} jobs to review  |  {datetime.now().strftime('%a %d %b %Y')}")
    print(f"  Keys: [a] approve  [s] skip  [l] later  [q] quit")
    print(f"{'═'*65}")

    for i, job in enumerate(pending, 1):
        job_id = str(job.get("job_id", ""))

        # Auto-approve high scorers
        if auto_approve_threshold and job.get("fit_score", 0) >= auto_approve_threshold:
            decisions[job_id] = "approved"
            approved.append(job)
            print(f"  AUTO-APPROVED [{job.get('fit_score', 0)}] {job.get('company')} — {job.get('title')}")
            continue

        _display_job(job, i, len(pending))

        while True:
            try:
                choice = input("  Action [a/s/l/q]: ").strip().lower()
            except (KeyboardInterrupt, EOFError):
                choice = "q"

            if choice in ("a", "approve", "y", "yes"):
                decisions[job_id] = "approved"
                approved.append(job)
                print("  → Approved ✓")
                break
            elif choice in ("s", "skip", "n", "no"):
                decisions[job_id] = "skipped"
                print("  → Skipped")
                break
            elif choice in ("l", "later"):
                decisions[job_id] = "later"
                print("  → Saved for later")
                break
            elif choice in ("q", "quit", "exit"):
                print(f"\n  Quit early. {len(approved)} approved so far.")
                _save_queue(decisions)
                submit_approved(approved)
                return approved
            else:
                print("  Type a (approve), s (skip), l (later), or q (quit)")

    _save_queue(decisions)

    print(f"\n{'═'*65}")
    print(f"  Review complete: {len(approved)} approved / {len(pending) - len(approved)} skipped")
    print(f"{'═'*65}")

    submit_approved(approved)
    return approved


def add_to_queue(jobs: list[dict]):
    """
    Append jobs to data/apply_queue.md for manual morning review.
    Called by run_daily.py after scraping.
    """
    if not jobs:
        return

    os.makedirs(DATA_DIR, exist_ok=True)
    queue_md = os.path.join(DATA_DIR, "apply_queue.md")
    date_str = datetime.now().strftime("%Y-%m-%d")

    with open(queue_md, "a", encoding="utf-8") as f:
        f.write(f"\n## Batch — {date_str} ({len(jobs)} jobs)\n\n")
        for job in jobs:
            score = job.get("fit_score", 0)
            f.write(f"- [ ] **{job.get('company', '')}** — {job.get('title', '')}\n")
            f.write(f"  Score: {score} | {job.get('location', '')} | {job.get('source', '')}\n")
            f.write(f"  URL: {job.get('url', '')}\n")
            if job.get("jd_snippet"):
                snippet = job["jd_snippet"][:200].replace("\n", " ")
                f.write(f"  JD: {snippet}...\n")
            f.write("  Decision: <!-- YES / SKIP / LATER -->\n\n")

    logger.info(f"Added {len(jobs)} jobs to {queue_md}")


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

    parser = argparse.ArgumentParser(description="shortlistr morning review queue")
    parser.add_argument("--auto", action="store_true",
                        help="Auto-approve jobs scoring 60+")
    parser.add_argument("--threshold", type=int, default=60,
                        help="Score threshold for --auto mode (default 60)")
    args = parser.parse_args()

    threshold = args.threshold if args.auto else 0
    run_review(auto_approve_threshold=threshold)
