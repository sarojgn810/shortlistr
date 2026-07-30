"""Per-source yield audit: how much each scraper pulls vs. how much is on target.

Run:  python3 -m automation.tools.source_audit [--source naukri] [--no-apify]

Prints raw count, on-target count, and why the rest were rejected, so a source
that is merely loud can be told apart from one that is actually productive.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config as cfg  # noqa: E402
from pipeline.filter import _title_matches, passes_title_location  # noqa: E402
from processors.job_filter import score_job  # noqa: E402
from sources.registry import _ADAPTERS  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")


def _reject_reason(job) -> str:
    if not _title_matches(job.title, cfg.SEARCH_KEYWORDS):
        return "title mismatch"
    location = (job.location or "").lower()
    if not location.strip():
        return "no location (should pass)"
    return "location mismatch"


def audit_source(name: str, cls) -> dict:
    t0 = time.monotonic()
    try:
        jobs, stats = cls().fetch_raw(log_totals=False)
    except Exception as e:  # a source that explodes is a finding, not a crash
        return {"source": name, "error": str(e)[:160], "raw": 0, "on_target": 0}

    passed, rejected = [], []
    for j in jobs:
        (passed if passes_title_location(j) else rejected).append(j)

    scored = 0
    for j in passed:
        try:
            if int(score_job(j.to_dict()).get("fit_score", 0)) >= cfg.MIN_FIT_SCORE:
                scored += 1
        except Exception:
            pass

    by_subsource = Counter((j.source or "?") for j in jobs)
    return {
        "source": name,
        "raw": len(jobs),
        "on_target": len(passed),
        "fit_ok": scored,
        "reasons": Counter(_reject_reason(j) for j in rejected).most_common(3),
        "sub": by_subsource.most_common(6),
        "sample": [f"{j.title} — {j.location or '?'}" for j in passed[:5]],
        "secs": round(time.monotonic() - t0, 1),
        "error": stats.error if getattr(stats, "error", None) else "",
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", action="append", help="limit to these adapter names")
    ap.add_argument("--no-apify", action="store_true", help="skip the paid Apify adapter")
    args = ap.parse_args()

    names = args.source or list(cfg.SOURCE_ENABLED)
    if args.no_apify:
        names = [n for n in names if n != "apify"]

    print(f"titles={cfg.SEARCH_KEYWORDS[:4]}… locations={cfg.LOCATION_KEYWORDS}")
    print(f"auditing: {names}\n")

    rows = []
    for name in names:
        cls = _ADAPTERS.get(name)
        if not cls:
            print(f"{name:<16} (no adapter registered)")
            continue
        r = audit_source(name, cls)
        rows.append(r)
        hit = (r["on_target"] / r["raw"] * 100) if r["raw"] else 0.0
        print(
            f"{r['source']:<16} raw={r['raw']:<6} on_target={r['on_target']:<5} "
            f"fit_ok={r.get('fit_ok', 0):<4} hit={hit:5.1f}%  {r['secs']}s"
        )
        if r.get("error"):
            print(f"    error: {r['error']}")
        if r.get("sub"):
            print(f"    by board: {r['sub']}")
        if r.get("reasons"):
            print(f"    rejected: {r['reasons']}")
        for s in r.get("sample", []):
            print(f"    hit: {s}")
        print()

    total_raw = sum(r["raw"] for r in rows)
    total_hit = sum(r["on_target"] for r in rows)
    print(f"TOTAL raw={total_raw} on_target={total_hit} "
          f"({(total_hit / total_raw * 100) if total_raw else 0:.1f}%)")


if __name__ == "__main__":
    main()
