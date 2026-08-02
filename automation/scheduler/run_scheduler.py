"""Background scheduler loop — checks scan interval and runs worker queue."""

from __future__ import annotations

import argparse
import logging
import time

from scheduler.scan_scheduler import tick_scheduler
from workers.discovery_worker import process_pending

logger = logging.getLogger(__name__)


def run_loop(*, interval_sec: int = 300, once: bool = False) -> None:
    while True:
        try:
            result = tick_scheduler()
            if result:
                logger.info(
                    "Scan complete: +%s jobs, %s evaluated",
                    result.get("added"),
                    result.get("evaluated"),
                )
            n = process_pending()
            if n:
                logger.info("Processed %s worker tasks", n)
        except Exception as exc:
            logger.error("Scheduler tick failed: %s", exc)
        if once:
            break
        time.sleep(interval_sec)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser(description="Shortlistr scan scheduler")
    p.add_argument("--once", action="store_true", help="Run one tick and exit")
    p.add_argument("--interval", type=int, default=300, help="Seconds between checks (default 300)")
    args = p.parse_args(argv)
    run_loop(interval_sec=args.interval, once=args.once)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
