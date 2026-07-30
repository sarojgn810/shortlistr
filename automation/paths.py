"""Repo-root path helpers shared by CLI tools."""

import os

from config import SHORTLISTR_ROOT, DATA_DIR, PIPELINE_PATH

PORTALS_PATH = os.path.join(SHORTLISTR_ROOT, "portals.yml")
SCAN_HISTORY_PATH = os.path.join(DATA_DIR, "scan-history.tsv")
APPLICATIONS_PATH = os.path.join(DATA_DIR, "applications.md")
LEGACY_APPLICATIONS_PATH = os.path.join(SHORTLISTR_ROOT, "applications.md")
ADDITIONS_DIR = os.path.join(SHORTLISTR_ROOT, "batch", "tracker-additions")
MERGED_DIR = os.path.join(ADDITIONS_DIR, "merged")
REPORTS_DIR = os.path.join(SHORTLISTR_ROOT, "reports")
OUTPUT_DIR = os.path.join(SHORTLISTR_ROOT, "output")
FONTS_DIR = os.path.join(SHORTLISTR_ROOT, "fonts")
CV_PATH = os.path.join(SHORTLISTR_ROOT, "cv.md")
PROFILE_PATH = os.path.join(SHORTLISTR_ROOT, "config", "profile.yml")
APPLICATIONS_TEMPLATE = os.path.join(SHORTLISTR_ROOT, "templates", "applications.example.md")


def applications_file() -> str:
    if os.path.exists(APPLICATIONS_PATH):
        return APPLICATIONS_PATH
    return LEGACY_APPLICATIONS_PATH
