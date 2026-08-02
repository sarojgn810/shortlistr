#!/bin/bash
# ============================================================
# Referral Engine — job inventory crons (non-interactive)
#
#   ingest      every 2 hours   discover + upsert (dedup by job_id)
#   jobs-sweep  daily 03:30     liveness check, archive dead, purge old archives
#
# Run once:  bash scripts/setup-job-crons.sh
# Remove:    bash scripts/setup-job-crons.sh --remove
#
# No prompts and no secrets: everything is read from .env / the OS keychain at
# runtime. (automation/setup_cron.sh is the LEGACY single-user daily job — it is
# interactive and installs run_daily.py; this script does not touch it.)
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$REPO_ROOT/logs"
MARKER="# shortlistr-referral-engine"

if [ "${1:-}" = "--remove" ]; then
  crontab -l 2>/dev/null | grep -v "$MARKER" | crontab - || true
  echo "✓ Removed referral-engine cron entries"
  crontab -l 2>/dev/null | grep "$MARKER" || echo "  (none remain)"
  exit 0
fi

mkdir -p "$LOG_DIR"

MAKE_BIN="$(command -v make || echo /usr/bin/make)"

# cron runs with a minimal PATH and no shell profile; cd into the repo and use
# absolute binaries so `make` and `python3` resolve.
INGEST_LINE="0 */2 * * * cd \"$REPO_ROOT\" && PATH=/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin $MAKE_BIN ingest >> \"$LOG_DIR/ingest.log\" 2>&1 $MARKER"
SWEEP_LINE="30 3 * * * cd \"$REPO_ROOT\" && PATH=/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin $MAKE_BIN jobs-sweep >> \"$LOG_DIR/sweep.log\" 2>&1 $MARKER"

( crontab -l 2>/dev/null | grep -v "$MARKER" || true
  echo "$INGEST_LINE"
  echo "$SWEEP_LINE"
) | crontab -

echo "✓ Installed referral-engine crons:"
crontab -l | grep "$MARKER" | sed 's/^/    /'
cat <<EOF

  Ingest:  every 2 hours          -> $LOG_DIR/ingest.log
  Sweep:   daily 03:30 local      -> $LOG_DIR/sweep.log

  Notes
    • Duplicate-safe: job identity is sha256(url) — a re-scrape updates in place.
    • Overlapping runs are skipped via a lock at data/.ingest.lock.
    • Dead jobs are archived after TWO consecutive failures, and only purged
      after 30 days if no referral/application/pipeline row references them.
    • Cron only fires while this Mac is awake.

  Verify:   crontab -l
  Try now:  make ingest ARGS=--dry-run
            make jobs-sweep ARGS="--limit 20 --dry-run"
  Remove:   bash scripts/setup-job-crons.sh --remove
EOF
