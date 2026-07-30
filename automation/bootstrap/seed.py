"""Idempotent first-run file seeding for local self-hosted install."""

from __future__ import annotations

import os
import shutil

from config import SHORTLISTR_ROOT, CV_MD_PATH, DATA_DIR
from paths import APPLICATIONS_TEMPLATE, PORTALS_PATH, PROFILE_PATH

PORTALS_TEMPLATE = os.path.join(SHORTLISTR_ROOT, "templates", "portals.example.yml")
PROFILE_EXAMPLE = os.path.join(SHORTLISTR_ROOT, "config", "profile.example.yml")
ENV_EXAMPLE = os.path.join(SHORTLISTR_ROOT, ".env.example")
ENV_FILE = os.path.join(SHORTLISTR_ROOT, ".env")
PROFILE_MD_TEMPLATE = os.path.join(SHORTLISTR_ROOT, "modes", "_profile.template.md")
PROFILE_MD = os.path.join(SHORTLISTR_ROOT, "modes", "_profile.md")
APPLICATIONS_PATH = os.path.join(DATA_DIR, "applications.md")


def _copy_if_missing(src: str, dst: str, label: str) -> str | None:
    if os.path.exists(dst):
        return None
    if not os.path.exists(src):
        return None
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)
    return f"Created {label}"


def _seed_starter_cv() -> str | None:
    """Write a clearly-placeholder cv.md so onboarding requires a real résumé."""
    if os.path.isfile(CV_MD_PATH):
        return None
    from cv.sample_content import DEFAULT_TEMPLATE_ID, PLACEHOLDER_CV

    os.makedirs(os.path.dirname(CV_MD_PATH) or SHORTLISTR_ROOT, exist_ok=True)
    with open(CV_MD_PATH, "w", encoding="utf-8") as f:
        f.write(PLACEHOLDER_CV.strip() + "\n")

    try:
        from cv.ats_score import score_ats_readiness
        from store.settings import set_cv_settings

        ats = score_ats_readiness(PLACEHOLDER_CV, template_id=DEFAULT_TEMPLATE_ID, include_template=True)
        set_cv_settings(
            {
                "template_id": DEFAULT_TEMPLATE_ID,
                "ats_score": ats["score"],
            }
        )
    except Exception:
        pass

    return "Created cv.md (placeholder — upload your résumé in onboarding)"


def seed_local_files() -> list[str]:
    """Create gitignored user-layer files from templates when missing."""
    import paths

    # Resolve paths at call time (not import time) so they honour the current
    # config/paths values — required for relocatable installs and testability.
    root = SHORTLISTR_ROOT
    data_dir = DATA_DIR
    portals_template = os.path.join(root, "templates", "portals.example.yml")
    env_example = os.path.join(root, ".env.example")
    env_file = os.path.join(root, ".env")
    profile_md_template = os.path.join(root, "modes", "_profile.template.md")
    profile_md = os.path.join(root, "modes", "_profile.md")
    applications_template = os.path.join(root, "templates", "applications.example.md")
    applications_path = os.path.join(data_dir, "applications.md")

    actions: list[str] = []

    for msg in (
        _copy_if_missing(portals_template, paths.PORTALS_PATH, "portals.yml"),
        _copy_if_missing(env_example, env_file, ".env"),
        _copy_if_missing(profile_md_template, profile_md, "modes/_profile.md"),
        _copy_if_missing(applications_template, applications_path, "data/applications.md"),
    ):
        if msg:
            actions.append(msg)

    os.makedirs(data_dir, exist_ok=True)
    os.makedirs(os.path.join(root, "output"), exist_ok=True)
    os.makedirs(os.path.join(root, "reports"), exist_ok=True)

    try:
        from store import db as store

        store.init_db()
    except Exception:
        pass

    cv_msg = _seed_starter_cv()
    if cv_msg:
        actions.append(cv_msg)

    # Do NOT seed config/profile.yml with a fictional person. Targeting must come
    # from onboarding / résumé upload so discovery never runs on author defaults.

    return actions


def main() -> int:
    actions = seed_local_files()
    if not actions:
        print("Bootstrap: all local files already present.")
        return 0
    print("Bootstrap seed:")
    for a in actions:
        print(f"  ✓ {a}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
