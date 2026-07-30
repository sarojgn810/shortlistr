#!/usr/bin/env python3
"""Setup validation for shortlistr (Python-only, ported from doctor.mjs)."""

from __future__ import annotations

import importlib.util
import os
import shutil
import sys

from config import SHORTLISTR_ROOT, PIPELINE_PATH
from paths import (
    APPLICATIONS_TEMPLATE,
    CV_PATH,
    FONTS_DIR,
    OUTPUT_DIR,
    PORTALS_PATH,
    PROFILE_PATH,
    REPORTS_DIR,
    applications_file,
)


def _green(s: str) -> str:
    return f"\x1b[32m{s}\x1b[0m" if sys.stdout.isatty() else s


def _red(s: str) -> str:
    return f"\x1b[31m{s}\x1b[0m" if sys.stdout.isatty() else s


def _dim(s: str) -> str:
    return f"\x1b[2m{s}\x1b[0m" if sys.stdout.isatty() else s


def check_python_version() -> dict:
    major, minor = sys.version_info[:2]
    if (major, minor) >= (3, 10):
        return {"pass": True, "label": f"Python >= 3.10 ({major}.{minor})"}
    return {
        "pass": False,
        "label": f"Python >= 3.10 required (found {major}.{minor})",
        "fix": "Install Python 3.10+",
    }


def check_playwright() -> dict:
    try:
        import playwright  # noqa: F401
    except ImportError:
        return {"pass": False, "label": "Playwright not installed", "fix": "Connections → Install Playwright"}

    # Check the chromium browser is downloaded by inspecting Playwright's browsers
    # directory. We deliberately do NOT start sync_playwright() here: it spawns a
    # driver subprocess, which raises NotImplementedError inside the server's async
    # event loop on Windows (and floods the log with tracebacks on every /setup/status).
    import glob

    base = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "")
    if not base:
        if os.name == "nt":
            base = os.path.join(os.environ.get("LOCALAPPDATA", ""), "ms-playwright")
        else:
            mac = os.path.expanduser("~/Library/Caches/ms-playwright")
            base = mac if os.path.isdir(mac) else os.path.expanduser("~/.cache/ms-playwright")
    if base and os.path.isdir(base) and (
        glob.glob(os.path.join(base, "chromium-*"))
        or glob.glob(os.path.join(base, "chromium_headless_shell-*"))
    ):
        return {"pass": True, "label": "Playwright chromium installed"}
    return {
        "pass": False,
        "label": "Playwright chromium not installed",
        "fix": "Connections → Install Playwright",
    }


def check_latex() -> dict:
    """A LaTeX engine is what makes the generated PDF match the .tex.

    Not fatal: without one, résumés still render through Chromium. But that is
    a different layout system from the templates, so the download and the
    on-screen preview stop being the same document — worth telling the user
    before an employer is the one who notices.
    """
    from cv.latex_builder import latex_available

    engine = latex_available()
    if engine:
        return {"pass": True, "label": f"LaTeX engine: {engine}"}
    return {
        "pass": False,
        "label": "No LaTeX engine — résumé PDFs fall back to the HTML renderer",
        "fix": ["Run: brew install tectonic", "Or install TeX Live (xelatex/pdflatex)"],
    }


def check_cv() -> dict:
    if os.path.exists(CV_PATH):
        return {"pass": True, "label": "cv.md found"}
    return {
        "pass": False,
        "label": "cv.md not found",
        "fix": ["Run: cd automation && python3 setup.py", "Or create cv.md in the project root"],
    }


def check_profile() -> dict:
    if os.path.exists(PROFILE_PATH):
        return {"pass": True, "label": "config/profile.yml found"}
    return {
        "pass": False,
        "label": "config/profile.yml not found",
        "fix": ["Run: cp config/profile.example.yml config/profile.yml", "Then edit it with your details"],
    }


def check_portals() -> dict:
    if os.path.exists(PORTALS_PATH):
        return {"pass": True, "label": "portals.yml found"}
    return {
        "pass": False,
        "label": "portals.yml not found",
        "fix": ["Run: cp templates/portals.example.yml portals.yml", "Then customize with your target companies"],
    }


def check_applications() -> dict:
    apps = applications_file()
    if os.path.exists(apps):
        return {"pass": True, "label": "data/applications.md found"}
    if os.path.exists(APPLICATIONS_TEMPLATE):
        try:
            os.makedirs(os.path.dirname(apps), exist_ok=True)
            shutil.copy2(APPLICATIONS_TEMPLATE, apps)
            return {"pass": True, "label": "data/applications.md created from template"}
        except OSError:
            pass
    return {
        "pass": False,
        "label": "data/applications.md not found",
        "fix": [
            "Run: cp templates/applications.example.md data/applications.md",
            "Or run: cd automation && python3 setup.py",
        ],
    }


def check_fonts() -> dict:
    if not os.path.isdir(FONTS_DIR):
        return {"pass": False, "label": "fonts/ directory not found", "fix": "The fonts/ directory is required for PDF generation"}
    if not os.listdir(FONTS_DIR):
        return {"pass": False, "label": "fonts/ directory is empty", "fix": "Add font files for PDF generation"}
    return {"pass": True, "label": "Fonts directory ready"}


def check_dir(name: str, path: str) -> dict:
    if os.path.isdir(path):
        return {"pass": True, "label": f"{name}/ directory ready"}
    try:
        os.makedirs(path, exist_ok=True)
        return {"pass": True, "label": f"{name}/ directory ready (auto-created)"}
    except OSError:
        return {"pass": False, "label": f"{name}/ directory could not be created", "fix": f"Run: mkdir {name}"}


def check_python_deps() -> dict:
    req_path = os.path.join(SHORTLISTR_ROOT, "automation", "requirements.txt")
    if not os.path.exists(req_path):
        return {"pass": True, "label": "automation/requirements.txt (skipped)"}
    missing = []
    for mod in ("yaml", "openpyxl", "requests", "playwright", "httpx"):
        if importlib.util.find_spec(mod) is None:
            missing.append(mod if mod != "yaml" else "PyYAML")
    if not missing:
        return {"pass": True, "label": "Python deps installed"}
    return {
        "pass": False,
        "label": f"Python deps missing ({', '.join(missing)})",
        "fix": "Run: pip3 install -r automation/requirements.txt && playwright install chromium",
    }


def check_config() -> dict:
    if PIPELINE_PATH.endswith("pipeline.md"):
        return {"pass": True, "label": "Python automation config loads (PIPELINE_PATH)"}
    return {
        "pass": False,
        "label": "Python automation config failed to load",
        "fix": ["Run: cp config/profile.example.yml config/profile.yml", "Or: cd automation && python3 setup.py"],
    }


def check_sqlite_store() -> dict:
    try:
        sys.path.insert(0, os.path.join(SHORTLISTR_ROOT, "automation"))
        from store import db as store
        store.init_db()
        return {"pass": True, "label": f"SQLite store ready ({store.DB_PATH})"}
    except Exception as e:
        return {"pass": False, "label": f"SQLite store failed: {e}", "fix": "Run: make migrate-markdown"}


def check_source_registry() -> dict:
    try:
        sys.path.insert(0, os.path.join(SHORTLISTR_ROOT, "automation"))
        from sources.registry import get_registry
        health = get_registry().health()
        enabled = [k for k, v in health.items() if v.get("enabled")]
        return {"pass": True, "label": f"Source registry ({len(enabled)} configured)"}
    except Exception as e:
        return {"pass": False, "label": f"Source registry failed: {e}"}


def check_httpx() -> dict:
    if importlib.util.find_spec("httpx") is not None:
        return {"pass": True, "label": "httpx installed (async fetch)"}
    return {
        "pass": False,
        "label": "httpx not installed",
        "fix": "Run: pip3 install httpx",
    }


def check_llm() -> dict:
    try:
        sys.path.insert(0, os.path.join(SHORTLISTR_ROOT, "automation"))
        from llm.status import llm_status

        st = llm_status()
        if st["available"]:
            return {"pass": True, "label": f"LLM ready ({st['provider']} / {st['model'] or 'default'})"}
        if st["configured"] and not st["api_key_set"]:
            return {
                "pass": False,
                "label": f"LLM provider '{st['provider']}' configured but SHORTLISTR_LLM_API_KEY missing",
                "fix": [
                    "Add SHORTLISTR_LLM_API_KEY to .env (repo root) or automation/.env",
                    "Then restart: make api",
                ],
            }
        if st["configured"]:
            return {
                "pass": False,
                "label": f"LLM configured ({st['provider']}) but unavailable — template eval only",
                "fix": "Check API key and pip install for provider package",
            }
        return {
            "pass": False,
            "label": "LLM provider is 'none' — template eval only",
            "fix": "Set llm.provider in config/profile.yml (openai, anthropic, gemini, grok, groq, ollama)",
        }
    except Exception as e:
        return {"pass": False, "label": f"LLM check failed: {e}"}


def main() -> int:
    print("\nautojob doctor")
    print("================\n")

    checks = [
        check_python_version(),
        check_python_deps(),
        check_playwright(),
        check_latex(),
        check_cv(),
        check_profile(),
        check_portals(),
        check_applications(),
        check_fonts(),
        check_dir("data", os.path.join(SHORTLISTR_ROOT, "data")),
        check_dir("output", OUTPUT_DIR),
        check_dir("reports", REPORTS_DIR),
        check_config(),
        check_sqlite_store(),
        check_source_registry(),
        check_httpx(),
        check_llm(),
    ]

    failures = 0
    for result in checks:
        if result["pass"]:
            print(f"{_green('✓')} {result['label']}")
        else:
            failures += 1
            print(f"{_red('✗')} {result['label']}")
            fixes = result.get("fix", [])
            if isinstance(fixes, str):
                fixes = [fixes]
            for hint in fixes:
                print(f"  {_dim('→ ' + hint)}")

    print("")
    if failures:
        print(f"Result: {failures} issue{'s' if failures != 1 else ''} found. Fix them and run `make doctor` again.")
        return 1
    print("Result: All checks passed. Run `/shortlistr` in your AI assistant or `make scan` to start.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
