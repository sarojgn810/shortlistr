"""
Interactive Job Queue Reviewer
Shows each PENDING job one at a time. Press one key to decide.

Usage:
    python3 processors/review_queue.py
    python3 processors/review_queue.py --submit   (review + submit YES jobs in one go)
"""

import json
import os
import sys
import subprocess
import termios
import tty
from datetime import datetime

# Ensure automation/ is on the path regardless of how the script is invoked
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import DATA_DIR
import processors.apply_queue as aq

# ── Terminal helpers ──────────────────────────────────────────────────────────

def _getch():
    """Read a single keypress without requiring Enter."""
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        return sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)

def _clear():
    os.system("clear")

def _color(text, code):
    return f"\x1b[{code}m{text}\x1b[0m"

def green(t):  return _color(t, "32")
def red(t):    return _color(t, "31")
def yellow(t): return _color(t, "33")
def cyan(t):   return _color(t, "36")
def bold(t):   return _color(t, "1")
def dim(t):    return _color(t, "2")


# ── Display ───────────────────────────────────────────────────────────────────

def _bar(char="─", width=58):
    return char * width

def _show_job(job, index, total):
    _clear()
    print()
    print(bold(f"  JOB REVIEW  —  {index} of {total}"))
    print(dim(f"  {_bar()}"))
    print()

    score = job.get("fit_score", 0)
    score_color = green if score >= 70 else (yellow if score >= 50 else red)

    print(f"  {bold('Company')}   {job.get('company', '?')}")
    print(f"  {bold('Title')}     {job.get('title', '?')}")
    print(f"  {bold('Score')}     {score_color(str(score) + '/100')}")
    print(f"  {bold('Salary')}    {job.get('salary') or dim('not listed')}")
    print(f"  {bold('Source')}    {job.get('source', '?')}")
    print(f"  {bold('Location')}  {job.get('location', '?')}")
    print(f"  {bold('Added')}     {job.get('date_added', '?')}")
    print()
    print(dim(f"  {_bar()}"))
    print(f"  {dim('Why matched:')}  {job.get('fit_reason', '?')}")

    snippet = (job.get("jd_snippet") or "").strip()
    if snippet:
        short = snippet[:120] + ("…" if len(snippet) > 120 else "")
        print(f"  {dim('JD preview:')}   {dim(short)}")

    print()
    print(dim(f"  {_bar()}"))
    print(f"  {bold('URL')}  {cyan(job.get('url', '?'))}")
    print()
    print(dim(f"  {_bar()}"))
    print()
    print(
        f"  {green(bold('[Y]'))} Apply   "
        f"{red(bold('[N]'))} Skip    "
        f"{yellow(bold('[S]'))} Later   "
        f"{bold('[O]')} Open in browser   "
        f"{bold('[Q]')} Quit"
    )
    print()
    print(f"  → ", end="", flush=True)


def _show_summary(yes, no, skip, remaining):
    _clear()
    print()
    print(bold("  ✅  Review complete!"))
    print()
    print(f"  {green('Applying to')}  : {yes} job(s)")
    print(f"  {red('Skipped')}      : {no} job(s)")
    print(f"  {yellow('Saved for later')}: {skip} job(s)")
    if remaining:
        print(f"  {dim('Still pending')} : {remaining} job(s) (you quit early)")
    print()


# ── Main reviewer ─────────────────────────────────────────────────────────────

def review(auto_submit=False):
    queue = aq._load_queue()
    pending = [j for j in queue if j["decision"] == "PENDING"]

    if not pending:
        _clear()
        print()
        print(bold("  📭  No jobs waiting for review."))
        print()
        total_yes = sum(1 for j in queue if j["decision"] == "YES")
        if total_yes:
            print(f"  You have {total_yes} job(s) already marked YES.")
            print(f"  To submit them: {cyan('python3 processors/apply_queue.py --submit')}")
        print()
        return

    yes_count = no_count = skip_count = 0
    url_map = {j["url"]: j for j in queue}

    for i, job in enumerate(pending, 1):
        _show_job(job, i, len(pending))

        while True:
            key = _getch().lower()

            if key == "y":
                url_map[job["url"]]["decision"] = "YES"
                yes_count += 1
                print(green("YES ✓"))
                break

            elif key == "n":
                url_map[job["url"]]["decision"] = "NO"
                no_count += 1
                print(red("NO ✗"))
                break

            elif key == "s":
                url_map[job["url"]]["decision"] = "SKIP"
                skip_count += 1
                print(yellow("SKIP →"))
                break

            elif key == "o":
                # Open URL in default browser — show job again after
                url = job.get("url", "")
                if url:
                    subprocess.run(["open", url], check=False)
                print(dim(" (opened in browser — press Y/N/S to decide)"))
                print(f"  → ", end="", flush=True)

            elif key in ("q", "\x03"):  # q or Ctrl+C
                remaining = len(pending) - i
                aq._save_queue(list(url_map.values()))
                aq._write_markdown(list(url_map.values()))
                _show_summary(yes_count, no_count, skip_count, remaining)
                print(dim("  Progress saved. Run again to continue.\n"))
                _maybe_submit(yes_count, auto_submit)
                return

    # All reviewed
    aq._save_queue(list(url_map.values()))
    aq._write_markdown(list(url_map.values()))
    _show_summary(yes_count, no_count, skip_count, 0)
    _maybe_submit(yes_count, auto_submit)


def _maybe_submit(yes_count, auto_submit):
    if yes_count == 0:
        return

    if auto_submit:
        print(bold("  Submitting YES jobs to shortlistr pipeline…"))
        approved = aq.submit_approved()
        print(green(f"  ✅  {len(approved)} job(s) sent to pipeline.\n"))
        return

    # Ask interactively
    print(f"  Submit {yes_count} YES job(s) to shortlistr pipeline now?")
    print(f"  {bold('[Y]')} Yes, submit   {bold('[N]')} Not yet")
    print(f"  → ", end="", flush=True)
    key = _getch().lower()
    print()
    if key == "y":
        approved = aq.submit_approved()
        print(green(f"\n  ✅  {len(approved)} job(s) sent to pipeline."))
    else:
        print(dim(f"  Not submitted. Run later: python3 processors/apply_queue.py --submit"))
    print()


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    auto_submit = "--submit" in sys.argv
    try:
        review(auto_submit=auto_submit)
    except KeyboardInterrupt:
        print("\n\n  Exited. Progress saved.\n")
