"""Blank-slate reset for local self-hosted install.

Moves all user-layer state (jobs DB, resume, profile, generated output) into a
timestamped backup folder, then re-initialises an empty database. Code, templates,
fonts, portals.yml, and your secrets (.env / OS keychain) are left untouched.

Run:  python -m automation.cli reset        (or: make reset)
"""

from __future__ import annotations

import os
import shutil
from datetime import datetime

from config import SHORTLISTR_ROOT, CV_MD_PATH, DATA_DIR, OUTPUT_DIR
from paths import PROFILE_PATH

# Files removed entirely (the dummy starter resume + profile + CV markdown).
_RESET_FILES = [
    CV_MD_PATH,
    os.path.join(SHORTLISTR_ROOT, "resume.pdf"),
    PROFILE_PATH,
    os.path.join(SHORTLISTR_ROOT, "modes", "_profile.md"),
]

# Directories emptied (contents moved to backup), keeping the dir + .gitkeep.
_RESET_DIRS = [
    DATA_DIR,
    OUTPUT_DIR,
    os.path.join(SHORTLISTR_ROOT, "reports"),
]

# Never touched — secrets and source config the user curates.
_PRESERVE = {".env", ".gitkeep", "portals.yml"}


def _backup_root() -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return os.path.join(SHORTLISTR_ROOT, ".reset-backup", stamp)


def reset_local(*, backup: bool = True) -> list[str]:
    actions: list[str] = []
    backup_root = _backup_root() if backup else None

    def _stash(path: str, rel: str) -> None:
        if not backup_root:
            return
        dest = os.path.join(backup_root, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copy2(path, dest)

    for path in _RESET_FILES:
        if os.path.isfile(path):
            _stash(path, os.path.relpath(path, SHORTLISTR_ROOT))
            os.remove(path)
            actions.append(f"Removed {os.path.relpath(path, SHORTLISTR_ROOT)}")

    for d in _RESET_DIRS:
        if not os.path.isdir(d):
            continue
        for name in os.listdir(d):
            if name in _PRESERVE:
                continue
            full = os.path.join(d, name)
            rel = os.path.relpath(full, SHORTLISTR_ROOT)
            if backup_root:
                dest = os.path.join(backup_root, rel)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                if os.path.isdir(full):
                    shutil.copytree(full, dest, dirs_exist_ok=True)
                else:
                    shutil.copy2(full, dest)
            if os.path.isdir(full):
                shutil.rmtree(full)
            else:
                os.remove(full)
            actions.append(f"Cleared {rel}")

    # Fresh empty database so the API starts clean.
    os.makedirs(DATA_DIR, exist_ok=True)
    try:
        from store import db as store

        store.init_db()
        actions.append("Re-initialised empty database")
    except Exception as e:  # pragma: no cover
        actions.append(f"DB init skipped: {e}")

    if backup_root and os.path.isdir(backup_root):
        actions.append(f"Backup saved to {os.path.relpath(backup_root, SHORTLISTR_ROOT)}")
    return actions


def main() -> int:
    actions = reset_local(backup=True)
    print("Blank-slate reset:")
    for a in actions:
        print(f"  - {a}")
    print("\nNext: run `make start` (or `make dev`) and open http://localhost:3000/onboarding")
    print("Secrets (.env / keychain) and portals.yml were preserved.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
