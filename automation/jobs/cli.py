"""CLI for the job inventory sweep: liveness check, archive, purge."""

from __future__ import annotations

import argparse
import logging


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="jobs-sweep",
        description="Check job liveness, archive dead listings, purge old archives",
    )
    p.add_argument("--limit", type=int, default=300, help="max URLs to check this run")
    p.add_argument("--recheck-after-hours", type=int, default=72)
    p.add_argument("--purge-days", type=int, default=30)
    p.add_argument("--no-purge", action="store_true", help="check/archive only")
    p.add_argument("--browser", action="store_true",
                   help="second-opinion Playwright check on uncertain verdicts (slow)")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from jobs.liveness_sweep import purge_archived, sweep

    res = sweep(
        limit=args.limit,
        recheck_after_hours=args.recheck_after_hours,
        dry_run=args.dry_run,
        use_browser=args.browser,
    )
    print(
        f"checked={res['checked']} live={res['live']} dead={res['dead']} "
        f"uncertain={res['uncertain']} archived={res['archived']}"
        + ("  (dry run)" if res["dry_run"] else "")
    )
    if not args.no_purge:
        pr = purge_archived(older_than_days=args.purge_days, dry_run=args.dry_run)
        print(f"purged={pr['purged']} (archived > {args.purge_days}d, unreferenced)"
              + ("  (dry run)" if pr["dry_run"] else ""))
    return 0
