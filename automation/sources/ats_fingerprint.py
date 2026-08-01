"""Fingerprint careers URLs / HTML for public ATS board tokens.

Used to grow ``portals.yml`` without hand-editing every Greenhouse/Lever/… slug.
Never wipes the user's portals file — only merges detected ATS fields.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any
from urllib.parse import urljoin

import requests
import yaml

from config import AUTOJOB_ROOT
from portals_config import PORTALS_PATH, parse_workday_url

logger = logging.getLogger(__name__)

# (ats_type, regex with one capture group for the board/company token)
_URL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("greenhouse", re.compile(r"boards-api\.greenhouse\.io/v1/boards/([^/?#]+)", re.I)),
    ("greenhouse", re.compile(r"job-boards(?:\.eu)?\.greenhouse\.io/([^/?#]+)", re.I)),
    ("greenhouse", re.compile(r"boards\.greenhouse\.io/([^/?#]+)", re.I)),
    ("lever", re.compile(r"jobs\.lever\.co/([^/?#]+)", re.I)),
    ("ashby", re.compile(r"jobs\.ashbyhq\.com/([^/?#]+)", re.I)),
    ("smartrecruiters", re.compile(r"careers\.smartrecruiters\.com/([^/?#]+)", re.I)),
    ("smartrecruiters", re.compile(r"jobs\.smartrecruiters\.com/([^/?#]+)", re.I)),
    ("recruitee", re.compile(r"([a-z0-9-]+)\.recruitee\.com", re.I)),
    ("teamtailor", re.compile(r"([a-z0-9-]+)\.teamtailor\.com", re.I)),
)


def fingerprint_url(url: str) -> dict[str, Any] | None:
    """Return ``{ats_type, token, careers_url, scan_method, api?}`` or None."""
    u = (url or "").strip()
    if not u:
        return None

    wd = parse_workday_url(u)
    if wd:
        tenant, wd_n, site = wd
        return {
            "ats_type": "workday",
            "token": f"{tenant}/{site}",
            "tenant": tenant,
            "wd": wd_n,
            "site": site,
            "careers_url": u.split("?")[0],
            "scan_method": "workday",
            "api": "",
        }

    for ats, pat in _URL_PATTERNS:
        m = pat.search(u)
        if not m:
            continue
        token = m.group(1)
        if ats == "greenhouse":
            api = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs"
            careers = f"https://job-boards.greenhouse.io/{token}"
        elif ats == "lever":
            api = f"https://api.lever.co/v0/postings/{token}"
            careers = f"https://jobs.lever.co/{token}"
        elif ats == "ashby":
            api = f"https://api.ashbyhq.com/posting-api/job-board/{token}?includeCompensation=true"
            careers = f"https://jobs.ashbyhq.com/{token}"
        elif ats == "smartrecruiters":
            api = f"https://api.smartrecruiters.com/v1/companies/{token}/postings"
            careers = f"https://careers.smartrecruiters.com/{token}"
        elif ats == "teamtailor":
            api = f"https://{token}.teamtailor.com/jobs.json"
            careers = f"https://{token}.teamtailor.com"
        else:  # recruitee
            api = f"https://{token}.recruitee.com/api/offers"
            careers = f"https://{token}.recruitee.com"
        return {
            "ats_type": ats,
            "token": token,
            "careers_url": careers,
            "scan_method": ats if ats != "greenhouse" else "api",
            "api": api,
        }
    return None


def fingerprint_html(html: str, base_url: str = "") -> dict[str, Any] | None:
    """Find the first ATS board link/iframe in page HTML."""
    if not html:
        return None
    # Prefer explicit board hosts over random links.
    hrefs = re.findall(r"""(?:href|src)=["']([^"']+)["']""", html, flags=re.I)
    candidates: list[str] = []
    for href in hrefs:
        full = urljoin(base_url, href)
        candidates.append(full)
    # Also scan raw text for board URLs pasted without href.
    for ats, pat in _URL_PATTERNS:
        for m in pat.finditer(html):
            candidates.append(m.group(0) if m.group(0).startswith("http") else urljoin(base_url, m.group(0)))
    if parse_workday_url(base_url):
        return fingerprint_url(base_url)
    for c in candidates:
        hit = fingerprint_url(c)
        if hit:
            return hit
    return fingerprint_url(base_url)


def scan_careers_url(url: str, *, timeout: float = 12.0) -> dict[str, Any]:
    """Fingerprint a careers URL (direct pattern, else fetch HTML)."""
    direct = fingerprint_url(url)
    if direct:
        return {"url": url, "ok": True, "hit": direct, "via": "url"}
    try:
        resp = requests.get(
            url,
            timeout=timeout,
            headers={"User-Agent": "AutojobATSFingerprint/1.0"},
            allow_redirects=True,
        )
        final = str(resp.url or url)
        hit = fingerprint_url(final) or fingerprint_html(resp.text or "", final)
        if hit:
            return {"url": url, "ok": True, "hit": hit, "via": "html", "final_url": final}
        return {"url": url, "ok": False, "hit": None, "via": "html", "final_url": final}
    except Exception as exc:
        return {"url": url, "ok": False, "hit": None, "error": str(exc)}


def _load_portals_doc() -> tuple[str, dict[str, Any]]:
    path = PORTALS_PATH if os.path.isfile(PORTALS_PATH) else os.path.join(
        AUTOJOB_ROOT, "templates", "portals.example.yml"
    )
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        data = {}
    return path, data


def propose_from_urls(urls: list[str], *, company_name: str = "") -> list[dict[str, Any]]:
    """Scan URLs and return merge proposals for the Portals UI."""
    out: list[dict[str, Any]] = []
    for url in urls:
        u = (url or "").strip()
        if not u:
            continue
        result = scan_careers_url(u)
        hit = result.get("hit")
        if not hit:
            out.append(
                {
                    "url": u,
                    "detected": False,
                    "error": result.get("error") or "No public ATS board found",
                }
            )
            continue
        name = company_name.strip() or hit["token"].replace("-", " ").title()
        proposal = {
            "url": u,
            "detected": True,
            "name": name,
            "ats_type": hit["ats_type"],
            "token": hit["token"],
            "careers_url": hit["careers_url"],
            "scan_method": hit.get("scan_method") or hit["ats_type"],
            "api": hit.get("api") or "",
            "notes": f"Auto-detected {hit['ats_type']} board ({hit['token']})",
            "enabled": True,
        }
        out.append(proposal)
    return out


def apply_proposals(proposals: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge detected ATS entries into portals.yml (additive / field update only)."""
    path, data = _load_portals_doc()
    # Live portals.yml uses tracked_companies (see AGENTS data contract).
    companies = data.get("tracked_companies")
    if not isinstance(companies, list):
        companies = []
        data["tracked_companies"] = companies

    added = 0
    updated = 0
    for prop in proposals:
        if not prop.get("detected"):
            continue
        name = str(prop.get("name") or "").strip()
        careers = str(prop.get("careers_url") or "").strip()
        if not name or not careers:
            continue
        existing = None
        for c in companies:
            if not isinstance(c, dict):
                continue
            if str(c.get("name") or "").strip().lower() == name.lower():
                existing = c
                break
            if str(c.get("careers_url") or "").strip().rstrip("/") == careers.rstrip("/"):
                existing = c
                break
        payload = {
            "name": name,
            "careers_url": careers,
            "scan_method": prop.get("scan_method") or "api",
            "notes": prop.get("notes") or "",
            "enabled": True,
        }
        if prop.get("api"):
            payload["api"] = prop["api"]
        if existing is None:
            companies.append(payload)
            added += 1
        else:
            for k, v in payload.items():
                if v:
                    existing[k] = v
            updated += 1

    # Always write to the live portals path (user layer).
    os.makedirs(os.path.dirname(PORTALS_PATH) or ".", exist_ok=True)
    with open(PORTALS_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    return {"path": PORTALS_PATH, "added": added, "updated": updated, "total": len(companies)}
