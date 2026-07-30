"""Scheduled job ingestion — the entry point cron calls every 2 hours.

Deliberately bypasses scan_scheduler.scan_is_due(): that helper has a 120s boot
grace which returns False forever while last_scan_at is NULL, so a one-shot cron
invocation would never fire its first scan. Cron owns the cadence here; the
scheduler daemon remains for interactive/long-running use.

Duplicate-safety comes from the store: job_id is sha256(url-without-query) and
upsert_jobs is INSERT … ON CONFLICT(id) DO UPDATE, so re-ingesting the same
posting updates it in place instead of creating a row.
"""

from __future__ import annotations

import errno
import fcntl
import logging
import os
from datetime import datetime, timezone

from config import DATA_DIR

logger = logging.getLogger(__name__)

LOCK_PATH = os.path.join(DATA_DIR, ".ingest.lock")
# Must stay under the 2h cron cadence: sources/fetcher.DEFAULT_TTL is exactly
# 7200s, so leaving it alone would serve a cached snapshot on every other tick.
INGEST_TTL_SECONDS = 3300


class _Lock:
    """Non-blocking inter-process lock so an overrunning tick is skipped, not stacked."""

    def __init__(self, path: str):
        self.path = path
        self._fh = None

    def __enter__(self) -> bool:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        self._fh = open(self.path, "w")
        try:
            fcntl.flock(self._fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as e:
            if e.errno in (errno.EACCES, errno.EAGAIN):
                self._fh.close()
                self._fh = None
                return False
            raise
        self._fh.write(f"{os.getpid()} {datetime.now(timezone.utc).isoformat()}\n")
        self._fh.flush()
        return True

    def __exit__(self, *exc) -> None:
        if self._fh:
            fcntl.flock(self._fh, fcntl.LOCK_UN)
            self._fh.close()


def run_ingest(*, dry_run: bool = False, ttl: int = INGEST_TTL_SECONDS) -> dict:
    """One ingestion pass: discover → filter → score → persist. Returns a summary."""
    from store import db as store

    prev_ttl = None
    try:
        import sources.fetcher as fetcher

        prev_ttl = fetcher.DEFAULT_TTL
        fetcher.DEFAULT_TTL = ttl
    except Exception:
        pass

    started = datetime.now(timezone.utc)
    run_id = None
    try:
        from orchestrator.discovery import discover_and_filter, persist_discovered

        run_id = store.start_run(dry_run=dry_run)
        passed, rejected, stats = discover_and_filter(log_totals=True)
        gate = stats.get("persist_gate") or {}
        persisted = 0 if dry_run else persist_discovered(passed, run_id=run_id)
        store.finish_run(
            run_id,
            source_stats=stats,
            discovered=int(gate.get("fetched") or (len(passed) + len(rejected))),
            passed=len(passed),
            strong_fit=sum(1 for j in passed if (j.fit_score or 0) >= 70),
        )
        return {
            "discovered": int(gate.get("fetched") or (len(passed) + len(rejected))),
            "passed": len(passed),
            "persisted": persisted,
            "kept": int(gate.get("kept") or len(passed)),
            "dropped_off_target": int(gate.get("dropped_off_target") or 0),
            "dropped_low_fit": int(gate.get("dropped_low_fit") or 0),
            "seconds": round((datetime.now(timezone.utc) - started).total_seconds(), 1),
            "dry_run": dry_run,
            "run_id": run_id,
        }
    except Exception as e:
        if run_id:
            try:
                store.finish_run(run_id, source_stats={}, discovered=0, passed=0,
                                 strong_fit=0, error=str(e))
            except Exception:
                pass
        raise
    finally:
        if prev_ttl is not None:
            try:
                import sources.fetcher as fetcher

                fetcher.DEFAULT_TTL = prev_ttl
            except Exception:
                pass


def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(prog="ingest", description="Scheduled job ingestion (cron)")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--ttl", type=int, default=INGEST_TTL_SECONDS,
                   help="HTTP cache TTL in seconds (keep below the cron interval)")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    with _Lock(LOCK_PATH) as acquired:
        if not acquired:
            logger.info("ingest: another run holds the lock — skipping this tick")
            return 0
        res = run_ingest(dry_run=args.dry_run, ttl=args.ttl)
    logger.info(
        "ingest: discovered=%(discovered)s passed=%(passed)s persisted=%(persisted)s "
        "in %(seconds)ss", res
    )
    return 0
