"""
Load ATS company slugs from portals.yml (single source of truth).

Falls back to templates/portals.example.yml when portals.yml is missing.
Used by scrapers, source adapters, and scan_portals.py.
"""

from __future__ import annotations

import os
import re

from config import SHORTLISTR_ROOT

PORTALS_PATH = os.path.join(SHORTLISTR_ROOT, "portals.yml")
PORTALS_EXAMPLE_PATH = os.path.join(SHORTLISTR_ROOT, "templates", "portals.example.yml")


def _resolve_portals_path() -> str | None:
    for path in (PORTALS_PATH, PORTALS_EXAMPLE_PATH):
        if os.path.exists(path):
            return path
    return None


def _slug_from_greenhouse_url(url: str) -> str | None:
    m = re.search(r"boards(?:-api)?(?:\.eu)?\.greenhouse\.io/v1/boards/([^/?#]+)", url)
    if m:
        return m.group(1)
    m = re.search(r"job-boards(?:\.eu)?\.greenhouse\.io/([^/?#]+)", url)
    if m:
        return m.group(1)
    return None


def _slug_from_lever_url(url: str) -> str | None:
    m = re.search(r"jobs\.lever\.co/([^/?#]+)", url)
    return m.group(1) if m else None


def _slug_from_ashby_url(url: str) -> str | None:
    m = re.search(r"jobs\.ashbyhq\.com/([^/?#]+)", url)
    return m.group(1) if m else None


def _parse_company(company: dict) -> tuple[str | None, str | None, str | None, str | None]:
    """Return (name, greenhouse_slug, lever_slug, ashby_slug)."""
    if company.get("enabled") is False:
        return None, None, None, None

    name = str(company.get("name", "") or "").strip() or None
    gh = lever = ashby = None
    api = company.get("api") or ""
    careers = company.get("careers_url") or ""

    if "greenhouse" in api:
        gh = _slug_from_greenhouse_url(api)
    if not gh:
        gh = _slug_from_greenhouse_url(careers)

    lever = _slug_from_lever_url(careers)
    ashby = _slug_from_ashby_url(careers)

    return name, gh, lever, ashby


def load_portals_slugs() -> tuple[set[str], set[str], set[str]]:
    """Parse portals file; return sets of greenhouse, lever, ashby slugs."""
    gh: set[str] = set()
    lever: set[str] = set()
    ashby: set[str] = set()

    path = _resolve_portals_path()
    if not path:
        return gh, lever, ashby

    try:
        import yaml

        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception:
        return gh, lever, ashby

    for company in data.get("tracked_companies") or []:
        if not isinstance(company, dict):
            continue
        _, g, l, a = _parse_company(company)
        if g:
            gh.add(g)
        if l:
            lever.add(l)
        if a:
            ashby.add(a)

    return gh, lever, ashby


def get_tracked_company_names() -> list[str]:
    """Company display names from portals.yml (for LinkedIn targeted search)."""
    path = _resolve_portals_path()
    if not path:
        return []

    try:
        import yaml

        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception:
        return []

    names: list[str] = []
    for company in data.get("tracked_companies") or []:
        if not isinstance(company, dict) or company.get("enabled") is False:
            continue
        name = str(company.get("name", "") or "").strip()
        if name:
            names.append(name)
    return names


def get_greenhouse_slugs() -> list[str]:
    gh, _, _ = load_portals_slugs()
    return sorted(gh)


def get_lever_slugs() -> list[str]:
    _, lever, _ = load_portals_slugs()
    return sorted(lever)


def get_ashby_slugs() -> list[str]:
    _, _, ashby = load_portals_slugs()
    return sorted(ashby)


def portals_summary() -> str:
    path = _resolve_portals_path()
    gh, lever, ashby = load_portals_slugs()
    if path:
        label = "portals.yml" if path == PORTALS_PATH else "portals.example.yml (fallback)"
        return f"{label}: {len(gh)} GH, {len(lever)} Lever, {len(ashby)} Ashby slugs"
    return "portals.yml: not found (no ATS watchlist slugs)"
