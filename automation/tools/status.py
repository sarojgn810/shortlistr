"""System status — last run, sources, pipeline counts."""

from __future__ import annotations

import json

from sources.circuit import all_status
from sources.registry import get_registry
from store import db as store


def format_status() -> str:
    store.init_db()
    lines = ["shortlistr status", "=" * 40]

    last = store.get_last_run()
    if last:
        lines.append(f"Last run:     {last.get('started_at', 'unknown')}")
        lines.append(f"  discovered: {last.get('jobs_discovered', 0)}")
        lines.append(f"  strong fit: {last.get('jobs_strong_fit', 0)}")
        try:
            stats = json.loads(last.get("source_stats_json") or "{}")
            if stats:
                lines.append("  sources:")
                for name, s in stats.items():
                    if name == "discovery_filter":
                        continue
                    err = s.get("error", "")
                    lines.append(
                        f"    {name}: raw={s.get('raw', 0)} records={s.get('records', 0)}"
                        + (f" ERR={err}" if err else "")
                    )
        except Exception:
            pass
    else:
        lines.append("Last run:     (none)")

    lines.append(f"Pipeline pending (DB): {store.pending_pipeline_count()}")

    breakdown = store.pipeline_breakdown()
    if any(breakdown.values()):
        lines.append("Pipeline breakdown:")
        for st in ("pending", "evaluated", "approved", "submitted", "skipped"):
            if breakdown.get(st):
                lines.append(f"  {st}: {breakdown[st]}")

    from store.status import application_status_counts
    app_counts = application_status_counts()
    if app_counts:
        lines.append("Applications:")
        for st, n in sorted(app_counts.items()):
            lines.append(f"  {st}: {n}")

    lines.append("\nSource registry:")
    for name, h in get_registry().health().items():
        lines.append(f"  {name}: {h}")

    circuits = all_status()
    if circuits:
        lines.append("\nCircuit breakers:")
        for name, c in circuits.items():
            if c.get("open"):
                lines.append(f"  {name}: OPEN (failures={c.get('failures', 0)})")

    return "\n".join(lines)


def main() -> int:
    print(format_status())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
