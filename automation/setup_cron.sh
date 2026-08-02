#!/bin/bash
# ============================================================
# shortlistr — Daily cron setup
# Run once: bash setup_cron.sh
# ============================================================

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SHORTLISTR_ROOT="$(dirname "$SCRIPT_DIR")"
PYTHON=$(which python3)
LOG_DIR="$SCRIPT_DIR/logs"
ZSHRC="$HOME/.zshrc"

PROFILE_EMAIL=$("$PYTHON" -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR')
try:
    from config import CANDIDATE
    print(CANDIDATE.get('email', '') or '')
except Exception:
    print('')
" 2>/dev/null || true)

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║       shortlistr — Daily Cron Setup                 ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""

# ── 1. Python dependencies ─────────────────────────────────
echo "► Installing Python dependencies..."
pip3 install -r "$SCRIPT_DIR/requirements.txt" --quiet --break-system-packages 2>/dev/null || \
pip3 install -r "$SCRIPT_DIR/requirements.txt" --quiet
echo "  ✓ Dependencies installed"
echo ""

# ── 2. LinkedIn password ───────────────────────────────────
echo "► LinkedIn password (for Easy Apply)"
if [ -n "$PROFILE_EMAIL" ]; then
  echo "  Account: $PROFILE_EMAIL (from config/profile.yml)"
else
  echo "  Account: your LinkedIn email (set LINKEDIN_EMAIL or run setup.py)"
fi
echo "  Leave blank to skip (LinkedIn scraping will be disabled)"
echo ""
read -rsp "  LinkedIn password (hidden): " LI_PASS
echo ""

if [ -n "$LI_PASS" ]; then
    LINKEDIN_PASSWORD="$LI_PASS" "$PYTHON" -c "import os,keyring; keyring.set_password('shortlistr','LINKEDIN_PASSWORD',os.environ['LINKEDIN_PASSWORD'])" \
      && echo "  ✓ Saved to OS keychain" \
      || echo "  ⚠ keychain unavailable — set env LINKEDIN_PASSWORD manually"
else
    echo "  ⚠ Skipped — set later in onboarding or the OS keychain"
fi
echo ""

# ── 3. Naukri password ─────────────────────────────────────
echo "► Naukri password"
if [ -n "$PROFILE_EMAIL" ]; then
  echo "  Account: $PROFILE_EMAIL (from config/profile.yml, or set NAUKRI_EMAIL)"
else
  echo "  Account: your Naukri email"
fi
echo "  Leave blank to skip"
echo ""
read -rsp "  Naukri password (hidden): " NK_PASS
echo ""

if [ -n "$NK_PASS" ]; then
    NAUKRI_PASSWORD="$NK_PASS" "$PYTHON" -c "import os,keyring; keyring.set_password('shortlistr','NAUKRI_PASSWORD',os.environ['NAUKRI_PASSWORD'])" \
      && echo "  ✓ Saved to OS keychain" \
      || echo "  ⚠ keychain unavailable — set env NAUKRI_PASSWORD manually"
else
    echo "  ⚠ Skipped — set later in onboarding or the OS keychain"
fi
echo ""

# ── 4. Check Gmail OAuth token ────────────────────────────
echo "► Checking Gmail OAuth token..."
if [ -f "$SCRIPT_DIR/gmail_token.pickle" ]; then
    echo "  ✓ gmail_token.pickle found"
else
    echo "  ⚠ No Gmail token found. Run setup_oauth.py first:"
    echo "    cd $SCRIPT_DIR && python3 setup_oauth.py"
fi
echo ""

# ── 5. Install Playwright browsers ────────────────────────
echo "► Installing Playwright Chromium (for LinkedIn/Naukri)..."
python3 -m playwright install chromium --quiet 2>/dev/null || \
playwright install chromium 2>/dev/null || \
echo "  ⚠ Run manually: pip3 install playwright && playwright install chromium"
echo "  ✓ Chromium ready"
echo ""

# ── 6. Install cron ───────────────────────────────────────
# Two jobs, and neither of them is run_daily.py. That legacy script may still
# discover and score, but it never auto-submits. CLAUDE.md's rule is that
# background jobs only discover, refresh and archive — nothing unattended may
# reach an employer.
#
#   ingest      every 2h. Forces a sub-2h TTL so alternate ticks cannot serve a
#               cached snapshot, and calls the orchestrator directly rather than
#               scan_is_due(), whose boot grace never opens on a one-shot run.
#   jobs-sweep  daily. Rechecks liveness and archives on a second dead verdict.
#               Without it the inbox fills with closed listings.
#
# Secrets are read from the OS keychain at runtime — never embedded in a
# crontab line. An older version of this script did embed one, and it sat in
# the crontab for months.
echo "► Installing background jobs (discovery every 2h, liveness sweep daily)..."

mkdir -p "$SHORTLISTR_ROOT/logs"

# launchd, not cron. This was cron until cron demonstrated it cannot work here:
# on current macOS it has no access to ~/Documents without Full Disk Access, so
# the very first scheduled run logged
#   make: getcwd: Operation not permitted
#   make: *** No rule to make target `ingest'
# and would have kept failing every two hours while looking scheduled. A
# LaunchAgent runs inside the user's session, which is the mechanism macOS
# actually supports, and it needs no `cd` because WorkingDirectory is explicit.
install_agent() {   # name, cli-command, interval-seconds
  local label="com.shortlistr.$1" cmd="$2" interval="$3"
  local plist="$HOME/Library/LaunchAgents/$label.plist"
  mkdir -p "$HOME/Library/LaunchAgents"
  cat > "$plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$label</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON</string><string>-m</string><string>automation.cli</string><string>$cmd</string>
  </array>
  <key>WorkingDirectory</key><string>$SHORTLISTR_ROOT</string>
  <key>StartInterval</key><integer>$interval</integer>
  <key>StandardOutPath</key><string>$SHORTLISTR_ROOT/logs/$1.log</string>
  <key>StandardErrorPath</key><string>$SHORTLISTR_ROOT/logs/$1.log</string>
  <key>ProcessType</key><string>Background</string>
  <key>LowPriorityIO</key><true/>
</dict>
</plist>
PLIST
  launchctl unload "$plist" 2>/dev/null || true
  launchctl load "$plist"
}

install_agent discovery ingest 7200
install_agent sweep jobs-sweep 86400

# Retire anything the older versions of this script left in cron, without
# touching entries that belong to something else.
(crontab -l 2>/dev/null | grep -v "run_daily.py" | grep -v "$SHORTLISTR_ROOT" \
   | grep -v "^# Shortlistr" || true) | crontab - 2>/dev/null || true

echo "  ✓ Background jobs installed"
echo ""

# ── 7. Verify ─────────────────────────────────────────────
echo "► Installed agents (last exit code should be 0):"
launchctl list | grep com.shortlistr || echo "  none — check the output above"
echo ""
echo "  If a run logs 'Operation not permitted', grant Full Disk Access to"
echo "  $PYTHON in System Settings → Privacy & Security."
echo ""

GMAIL_LINE="Gmail OAuth (config/profile.yml email)"
[ -n "$PROFILE_EMAIL" ] && GMAIL_LINE="Gmail OAuth ($PROFILE_EMAIL)"

echo "╔══════════════════════════════════════════════════╗"
echo "║  Setup complete                                  ║"
echo "║                                                  ║"
echo "║  • Runs daily at 9 AM IST                        ║"
echo "║  • Email: $GMAIL_LINE"
echo "║  • Logs: automation/logs/                        ║"
echo "║  • Tracker: data/Job_Application_Tracker.xlsx  ║"
echo "║  • Pipeline: data/pipeline.md                    ║"
echo "║                                                  ║"
echo "║  Manual runs:                                    ║"
echo "║    Prefer: make ingest / dashboard Discover       ║"
echo "║    Legacy: python3 run_daily.py --dry-run         ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""
