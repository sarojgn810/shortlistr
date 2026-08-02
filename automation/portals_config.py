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


_WORKDAY_URL_RE = re.compile(
    r"https?://([a-z0-9-]+)\.wd(\d+)\.myworkdayjobs\.com/"
    r"(?:[a-z]{2}-[A-Z]{2}/)?"  # optional locale like en-US/
    r"([^/?#]+)",
    re.I,
)


def parse_workday_url(url: str) -> tuple[str, str, str] | None:
    """Return (tenant, wd_number, site) from a myworkdayjobs.com careers URL."""
    m = _WORKDAY_URL_RE.search(url or "")
    if not m:
        return None
    return m.group(1).lower(), m.group(2), m.group(3)


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


def _slug_from_smartrecruiters_url(url: str) -> str | None:
    m = re.search(
        r"(?:careers|jobs)\.smartrecruiters\.com/([^/?#]+)",
        url or "",
        re.I,
    )
    return m.group(1) if m else None


def _slug_from_recruitee_url(url: str) -> str | None:
    m = re.search(r"https?://([a-z0-9-]+)\.recruitee\.com", url or "", re.I)
    return m.group(1) if m else None


def get_smartrecruiters_slugs() -> list[str]:
    """Board company tokens from portals.yml SmartRecruiters careers URLs."""
    path = _resolve_portals_path()
    if not path:
        return []
    try:
        import yaml

        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception:
        return []
    out: set[str] = set()
    for company in data.get("tracked_companies") or []:
        if not isinstance(company, dict) or company.get("enabled") is False:
            continue
        url = str(company.get("api") or company.get("careers_url") or "")
        method = str(company.get("scan_method") or "").lower()
        slug = _slug_from_smartrecruiters_url(url)
        if slug or method == "smartrecruiters":
            if slug:
                out.add(slug)
            elif method == "smartrecruiters":
                # Explicit method without parseable URL — try name slug
                name = str(company.get("name") or "").strip().lower().replace(" ", "")
                if name:
                    out.add(name)
    return sorted(out)


def get_recruitee_slugs() -> list[str]:
    path = _resolve_portals_path()
    if not path:
        return []
    try:
        import yaml

        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception:
        return []
    out: set[str] = set()
    for company in data.get("tracked_companies") or []:
        if not isinstance(company, dict) or company.get("enabled") is False:
            continue
        url = str(company.get("api") or company.get("careers_url") or "")
        method = str(company.get("scan_method") or "").lower()
        slug = _slug_from_recruitee_url(url)
        if slug:
            out.add(slug)
        elif method == "recruitee":
            name = str(company.get("name") or "").strip().lower().replace(" ", "-")
            if name:
                out.add(name)
    return sorted(out)


def _slug_from_teamtailor_url(url: str) -> str | None:
    m = re.search(r"https?://([a-z0-9-]+)\.teamtailor\.com", url or "", re.I)
    return m.group(1) if m else None


def get_teamtailor_slugs() -> list[str]:
    path = _resolve_portals_path()
    if not path:
        return []
    try:
        import yaml

        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception:
        return []
    out: set[str] = set()
    for company in data.get("tracked_companies") or []:
        if not isinstance(company, dict) or company.get("enabled") is False:
            continue
        url = str(company.get("api") or company.get("careers_url") or "")
        method = str(company.get("scan_method") or "").lower()
        slug = _slug_from_teamtailor_url(url)
        if slug:
            out.add(slug)
        elif method == "teamtailor":
            name = str(company.get("name") or "").strip().lower().replace(" ", "-")
            if name:
                out.add(name)
    return sorted(out)


def get_workday_boards() -> list[tuple[str, str, str, str]]:
    """Return Workday boards as (tenant, wd_number, site, display_name).

    Accepts either ``scan_method: workday`` or a careers_url / api on
    ``*.myworkdayjobs.com``.
    """
    path = _resolve_portals_path()
    if not path:
        return []

    try:
        import yaml

        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception:
        return []

    out: list[tuple[str, str, str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for company in data.get("tracked_companies") or []:
        if not isinstance(company, dict) or company.get("enabled") is False:
            continue
        method = str(company.get("scan_method") or "").strip().lower()
        url = str(company.get("api") or company.get("careers_url") or "")
        parsed = parse_workday_url(url)
        if not parsed and method != "workday":
            continue
        if not parsed:
            continue
        tenant, wd_n, site = parsed
        key = (tenant, wd_n, site.lower())
        if key in seen:
            continue
        seen.add(key)
        name = str(company.get("name") or "").strip() or tenant.title()
        out.append((tenant, wd_n, site, name))
    return out


def get_websearch_company_queries(
    portals_path: str | None = None,
    *,
    limit: int = 8,
) -> tuple[list[dict], dict]:
    """Load tracked_companies that rely on scan_method: websearch.

    These rows were never read by discovery — watchlist_ats only extracts
    Greenhouse/Lever/Ashby slugs — so branded careers pages sat as dead config.
    """
    path = portals_path or _resolve_portals_path()
    stats = {"companies": 0, "with_query": 0, "skipped_no_query": 0, "capped": 0}
    if not path:
        return [], stats

    try:
        import yaml

        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception:
        return [], stats

    queries: list[dict] = []
    for company in data.get("tracked_companies") or []:
        if not isinstance(company, dict) or company.get("enabled") is False:
            continue
        method = str(company.get("scan_method") or "").strip().lower()
        if method != "websearch":
            continue
        stats["companies"] += 1
        query = str(company.get("scan_query") or "").strip()
        name = str(company.get("name") or "").strip() or "company"
        if not query:
            stats["skipped_no_query"] += 1
            continue
        stats["with_query"] += 1
        if len(queries) >= max(0, limit):
            stats["capped"] += 1
            continue
        queries.append({
            "query": query,
            "name": f"company:{name}",
            "company": name,
        })
    return queries, stats


def portals_summary() -> str:
    path = _resolve_portals_path()
    gh, lever, ashby = load_portals_slugs()
    workday = get_workday_boards()
    sr = get_smartrecruiters_slugs()
    rt = get_recruitee_slugs()
    tt = get_teamtailor_slugs()
    if path:
        label = "portals.yml" if path == PORTALS_PATH else "portals.example.yml (fallback)"
        return (
            f"{label}: {len(gh)} GH, {len(lever)} Lever, {len(ashby)} Ashby, "
            f"{len(workday)} Workday, {len(sr)} SmartRecruiters, {len(rt)} Recruitee, "
            f"{len(tt)} Teamtailor"
        )
    return "portals.yml: not found (no ATS watchlist slugs)"
