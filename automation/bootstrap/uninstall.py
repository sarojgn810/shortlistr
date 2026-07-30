"""Uninstall / remove Shortlistr from this machine.

Stops optional background hooks, clears OS-keychain secrets Shortlistr stored,
and prints the remaining manual steps (delete the repo folder, optional
Playwright / Node / Python cleanup).

  make uninstall                 # guided cleanup + print remaining steps
  python -m automation.cli uninstall --purge-data   # also wipe local user data

This never deletes the repository directory itself — you remove that last.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys

from config import SHORTLISTR_ROOT, DATA_DIR, OUTPUT_DIR
from paths import PROFILE_PATH
from secrets_store import KNOWN_SECRETS, delete_secret


def _stop_local_servers() -> list[str]:
    """Best-effort: free the default Shortlistr ports. Never raises."""
    actions: list[str] = []
    for port in (3000, 8787):
        try:
            out = subprocess.check_output(
                ["lsof", "-ti", f"tcp:{port}"],
                stderr=subprocess.DEVNULL,
                text=True,
            ).strip()
        except (subprocess.CalledProcessError, FileNotFoundError, OSError):
            continue
        pids = [p for p in out.splitlines() if p.strip()]
        for pid in pids:
            try:
                os.kill(int(pid), 15)
                actions.append(f"Stopped process on :{port} (pid {pid})")
            except (ProcessLookupError, ValueError, PermissionError, OSError):
                pass
    return actions


def _remove_crons() -> list[str]:
    actions: list[str] = []
    script = os.path.join(SHORTLISTR_ROOT, "scripts", "setup-job-crons.sh")
    if os.path.isfile(script):
        try:
            subprocess.run(
                ["bash", script, "--remove"],
                check=False,
                cwd=SHORTLISTR_ROOT,
                capture_output=True,
                text=True,
            )
            actions.append("Removed Shortlistr cron entries (if any)")
        except OSError as e:
            actions.append(f"Cron cleanup skipped: {e}")
    # Legacy markers (shortlistr + older autojob clones)
    try:
        current = subprocess.check_output(["crontab", "-l"], stderr=subprocess.DEVNULL, text=True)
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return actions
    markers = (
        "# shortlistr",
        "# autojob-referral-engine",
        "# autojob",
        "automation.cli ingest",
        "run_daily.py",
    )
    if not any(m in current for m in markers):
        return actions
    kept = [
        ln
        for ln in current.splitlines()
        if "# shortlistr" not in ln
        and "# autojob-referral-engine" not in ln
        and "run_daily.py" not in ln
        and "automation.cli ingest" not in ln
        and "jobs-sweep" not in ln
    ]
    try:
        proc = subprocess.run(
            ["crontab", "-"],
            input="\n".join(kept) + ("\n" if kept else ""),
            text=True,
            check=False,
            capture_output=True,
        )
        if proc.returncode == 0:
            actions.append("Stripped leftover Shortlistr lines from crontab")
    except OSError:
        pass
    return actions


def _clear_keychain() -> list[str]:
    cleared: list[str] = []
    for name in KNOWN_SECRETS:
        try:
            delete_secret(name)
            cleared.append(name)
        except Exception:
            pass
    if cleared:
        return [f"Cleared OS keychain secrets: {', '.join(cleared)}"]
    return ["No Shortlistr keychain secrets found (or keyring unavailable)"]


def _purge_user_data() -> list[str]:
    """Destructive: wipe local user-layer files (no backup)."""
    actions: list[str] = []
    targets = [
        os.path.join(SHORTLISTR_ROOT, "cv.md"),
        os.path.join(SHORTLISTR_ROOT, "resume.pdf"),
        PROFILE_PATH,
        os.path.join(SHORTLISTR_ROOT, "modes", "_profile.md"),
        os.path.join(SHORTLISTR_ROOT, "portals.yml"),
        os.path.join(SHORTLISTR_ROOT, ".env"),
        os.path.join(SHORTLISTR_ROOT, "automation", ".env"),
    ]
    for path in targets:
        if os.path.isfile(path):
            os.remove(path)
            actions.append(f"Deleted {os.path.relpath(path, SHORTLISTR_ROOT)}")

    for d in (
        DATA_DIR,
        OUTPUT_DIR,
        os.path.join(SHORTLISTR_ROOT, "reports"),
        os.path.join(SHORTLISTR_ROOT, "interview-prep"),
        os.path.join(SHORTLISTR_ROOT, ".reset-backup"),
        os.path.join(SHORTLISTR_ROOT, "logs"),
    ):
        if os.path.isdir(d):
            shutil.rmtree(d, ignore_errors=True)
            actions.append(f"Removed {os.path.relpath(d, SHORTLISTR_ROOT)}/")
    return actions


def _purge_build_artifacts() -> list[str]:
    actions: list[str] = []
    for rel in (
        "dashboard/node_modules",
        "dashboard/.next",
        "dashboard/.turbo",
        ".pytest_cache",
        ".coverage",
        "htmlcov",
    ):
        path = os.path.join(SHORTLISTR_ROOT, rel)
        if os.path.exists(path):
            shutil.rmtree(path, ignore_errors=True)
            actions.append(f"Removed {rel}/")
    for root, dirs, _files in os.walk(os.path.join(SHORTLISTR_ROOT, "automation")):
        if "__pycache__" in dirs:
            shutil.rmtree(os.path.join(root, "__pycache__"), ignore_errors=True)
            dirs.remove("__pycache__")
    actions.append("Cleared automation/__pycache__ trees")
    return actions


def remaining_steps(*, purged_data: bool) -> str:
    repo = SHORTLISTR_ROOT
    return f"""
────────────────────────────────────────────────────────────
Shortlistr cleanup finished. Complete removal with these steps:

1) Quit Shortlistr
   Close the dashboard tab and any terminal still running
   `make start` / `make api` / `make dashboard-dev`.

2) Delete the project folder (this removes the app)
   rm -rf "{repo}"

   Windows (PowerShell), from the parent folder:
   Remove-Item -Recurse -Force .\\shortlistr

3) Optional — remove Playwright’s Chromium download
   (shared cache; only if nothing else needs Playwright)
   python3 -m playwright uninstall chromium
   # or delete: ~/Library/Caches/ms-playwright   (macOS)
   #            ~/.cache/ms-playwright           (Linux)
   #            %USERPROFILE%\\AppData\\Local\\ms-playwright  (Windows)

4) Optional — uninstall Python / Node packages you installed only for Shortlistr
   pip3 uninstall -y -r "{os.path.join(repo, 'automation', 'requirements.txt')}"
   # Node: deleting dashboard/node_modules (already done unless you passed --keep-build)
   # is enough; you do not need to uninstall Node itself.

5) Optional — Local AI (Ollama) models Shortlistr may have pulled
   ollama list
   ollama rm <model-name>     # only models you no longer want

{"Data note: --purge-data already wiped résumé, profile, DB, .env, portals.yml, and backups." if purged_data else "Data note: your résumé, profile, DB, .env, and portals.yml are still in the folder until you delete it (step 2). To wipe them first: make uninstall ARGS=--purge-data"}

Nothing phones home. After step 2, Shortlistr is gone from this machine.
────────────────────────────────────────────────────────────
""".strip()


def uninstall_local(
    *,
    purge_data: bool = False,
    purge_build: bool = True,
    stop_servers: bool = True,
) -> list[str]:
    actions: list[str] = []
    if stop_servers:
        actions.extend(_stop_local_servers())
    actions.extend(_remove_crons())
    actions.extend(_clear_keychain())
    if purge_build:
        actions.extend(_purge_build_artifacts())
    if purge_data:
        actions.extend(_purge_user_data())
    return actions


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Remove Shortlistr from this machine")
    parser.add_argument(
        "--purge-data",
        action="store_true",
        help="Also delete résumé, profile, DB, .env, portals.yml, and backups (no restore)",
    )
    parser.add_argument(
        "--keep-build",
        action="store_true",
        help="Leave dashboard/node_modules and .next in place",
    )
    parser.add_argument(
        "--no-stop",
        action="store_true",
        help="Do not try to stop processes on :3000 / :8787",
    )
    args = parser.parse_args(argv)

    actions = uninstall_local(
        purge_data=bool(args.purge_data),
        purge_build=not bool(args.keep_build),
        stop_servers=not bool(args.no_stop),
    )
    print("Shortlistr uninstall:")
    for a in actions:
        print(f"  - {a}")
    print()
    print(remaining_steps(purged_data=bool(args.purge_data)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
