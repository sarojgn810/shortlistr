"""Apify job-board registry — opt-in actors mapped to Shortlistr sources.

Greenhouse / Lever / Ashby stay on the free local ATS adapters (watchlist_ats).
Workday needs per-company board URLs and is left for a later pass.
"""

from __future__ import annotations

from typing import Any, Callable
from urllib.parse import quote_plus

# Board id → display source label + default actor + input builder.
# Input builders receive (title, location, *, limit, experience, wants_remote, cfg).

BoardInputFn = Callable[..., dict[str, Any]]


def _naukri_input(
    title: str,
    location: str,
    *,
    limit: int,
    experience: int,
    wants_remote: bool,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    has_onsite = bool(location and location.lower() not in {"remote", "anywhere"})
    if wants_remote and has_onsite:
        wfh = ["0", "2", "3"]
    elif wants_remote:
        wfh = ["2", "3"]
    else:
        wfh = ["0"]
    return {
        "keywords": title,
        "location": location,
        "experience": experience,
        "limit": limit,
        "wfhType": wfh,
    }


def _linkedin_input(
    title: str,
    location: str,
    *,
    limit: int,
    experience: int,
    wants_remote: bool,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    return {
        "title": title,
        "location": location,
        "limit": min(limit, 100),
        "remote": ["2", "3"] if wants_remote else ["1"],
    }


def _indeed_input(
    title: str,
    location: str,
    *,
    limit: int,
    experience: int,
    wants_remote: bool,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    # India-first when the user is searching Bangalore/Bengaluru.
    loc_l = (location or "").lower()
    country = "in" if any(x in loc_l for x in ("bangalore", "bengaluru", "india", "mumbai", "hyderabad", "pune", "chennai", "delhi", "gurgaon", "gurugram")) else "us"
    return {
        "country": country,
        "title": title,
        "location": location or ("Remote" if wants_remote else ""),
        "limit": min(limit, 100),
        "datePosted": str(cfg.get("date_posted") or "14"),
    }


def _naukrigulf_input(
    title: str,
    location: str,
    *,
    limit: int,
    experience: int,
    wants_remote: bool,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    return {
        "keywords": title,
        "platform": "naukrigulf",
        "location": location or "",
        "experience": experience,
        "maxResults": limit,
        "freshness": "30d",
        "includeDescription": True,
        "dedupe": True,
    }


def _dice_input(
    title: str,
    location: str,
    *,
    limit: int,
    experience: int,
    wants_remote: bool,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    # parseforge/dice-scraper accepts search URLs or filters.
    q = quote_plus(title)
    loc = quote_plus(location or "Remote")
    url = f"https://www.dice.com/jobs?q={q}&location={loc}"
    if wants_remote:
        url += "&filters.workplaceTypes=Remote"
    return {
        "startUrls": [{"url": url}],
        "maxItems": limit,
    }


def _monster_input(
    title: str,
    location: str,
    *,
    limit: int,
    experience: int,
    wants_remote: bool,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    # bebity/monster-jobs-scraper — rental actor; fails soft if unpaid.
    out: dict[str, Any] = {
        "keyword": title,
        "location": location or ("Remote" if wants_remote else ""),
        "countryCode": str(cfg.get("monster_country") or "en_us"),
        "maxRows": min(limit, 100),
        "proxy": {"useApifyProxy": True},
    }
    if wants_remote:
        out["remoteWorkType"] = "REMOTE"
    return out


def _glassdoor_input(
    title: str,
    location: str,
    *,
    limit: int,
    experience: int,
    wants_remote: bool,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    # canadesk/glassdoor-ziprecruiter — engines "1" = Glassdoor (rental).
    city = location or ("Remote" if wants_remote else "Bengaluru")
    return {
        "title": title,
        "city": city,
        "country": str(cfg.get("glassdoor_country") or "India"),
        "engines": "1",
        "jobtype": "fulltime",
        "remote": "Yes" if wants_remote else "No",
        "max": min(limit, 50),
        "proxy": {"useApifyProxy": True},
    }


def _ziprecruiter_input(
    title: str,
    location: str,
    *,
    limit: int,
    experience: int,
    wants_remote: bool,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    # Same actor, engines "2" = ZipRecruiter (US/CA-heavy; rental).
    city = location or ("Remote" if wants_remote else "San Francisco")
    return {
        "title": title,
        "city": city,
        "country": str(cfg.get("zip_country") or "USA"),
        "engines": "2",
        "jobtype": "fulltime",
        "remote": "Yes" if wants_remote else "No",
        "max": min(limit, 50),
        "proxy": {"useApifyProxy": True},
    }


def _seek_input(
    title: str,
    location: str,
    *,
    limit: int,
    experience: int,
    wants_remote: bool,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    q = quote_plus(title)
    loc = quote_plus(location or "All Australia")
    return {
        "searchUrl": f"https://www.seek.com.au/{q}-jobs/in-{loc}",
        "maxItems": limit,
    }


def _upwork_input(
    title: str,
    location: str,
    *,
    limit: int,
    experience: int,
    wants_remote: bool,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    q = quote_plus(title)
    return {
        "mode": "lite",
        "startUrls": [{"url": f"https://www.upwork.com/nx/search/jobs/?q={q}&sort=recency"}],
        "maxItems": limit,
    }


def _hackernews_input(
    title: str,
    location: str,
    *,
    limit: int,
    experience: int,
    wants_remote: bool,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    # Keyword filter on the monthly Who is Hiring thread.
    query = title
    if wants_remote and "remote" not in query.lower():
        query = f"{title} remote"
    return {
        "mode": "hiring",
        "query": query,
        "maxItems": limit,
    }


# Boards we wire today. Keys are what users put under sources.apify.boards.
BOARD_REGISTRY: dict[str, dict[str, Any]] = {
    "linkedin": {
        "label": "LinkedIn",
        "actor": "valig/linkedin-jobs-scraper",
        "input": _linkedin_input,
        "notes": "Logged-out LinkedIn search.",
    },
    "naukri": {
        "label": "Naukri",
        "actor": "valig/naukri-jobs-scraper",
        "input": _naukri_input,
        "notes": "India board — richest salary/skills payload.",
    },
    "naukrigulf": {
        "label": "Naukrigulf",
        "actor": "k1ra/naukri-jobs-scraper",
        "input": _naukrigulf_input,
        "notes": "GCC / UAE twin of Naukri.",
    },
    "indeed": {
        "label": "Indeed",
        "actor": "valig/indeed-jobs-scraper",
        "input": _indeed_input,
        "notes": "Global + India (country=in when location is Indian).",
    },
    "dice": {
        "label": "Dice",
        "actor": "parseforge/dice-scraper",
        "input": _dice_input,
        "notes": "US tech board.",
    },
    "monster": {
        "label": "Monster",
        "actor": "bebity/monster-jobs-scraper",
        "input": _monster_input,
        "notes": "Rental actor (~$20/mo) — fail soft if unpaid; 0% store success historically.",
    },
    "seek": {
        "label": "Seek",
        "actor": "easyapi/seek-job-scraper",
        "input": _seek_input,
        "notes": "AU/NZ board.",
    },
    "upwork": {
        "label": "Upwork",
        "actor": "the-empire-strikes-back/upwork-scraper",
        "input": _upwork_input,
        "notes": "Freelance gigs — different shape from full-time roles.",
    },
    "hackernews": {
        "label": "Hacker News",
        "actor": "agency-shift/hackernews-jobs-ask-scraper",
        "input": _hackernews_input,
        "notes": "Monthly Who is Hiring thread via Algolia.",
    },
    "glassdoor": {
        "label": "Glassdoor",
        "actor": "canadesk/glassdoor-ziprecruiter",
        "input": _glassdoor_input,
        "notes": "Optional extra — rental actor; engines=1. Not in default boards.",
    },
    "ziprecruiter": {
        "label": "ZipRecruiter",
        "actor": "canadesk/glassdoor-ziprecruiter",
        "input": _ziprecruiter_input,
        "notes": "Optional extra — rental actor; engines=2; US/CA. Not in default boards.",
    },
}

# Documented but not wired as Apify boards — local adapters already cover them,
# or they need per-company board URLs we don't invent.
BOARD_SKIPPED: dict[str, str] = {
    "greenhouse": "Use local watchlist_ats (free public API) — portals.yml companies.",
    "lever": "Use local watchlist_ats (free public API) — portals.yml companies.",
    "ashby": "Use local watchlist_ats (free public GraphQL) — portals.yml companies.",
    "workday": "Needs per-company careers boardUrl; add later from portals.yml Workday entries.",
    "remotive": "Already covered free via local aggregators adapter.",
    "himalayas": "Already covered free via local aggregators adapter.",
    "remoteok": "Already covered free via local aggregators adapter.",
}

# Sensible default: India SRE path + LinkedIn. Extra boards are opt-in.
DEFAULT_BOARDS = ["naukri", "linkedin", "indeed"]


def known_board_ids() -> list[str]:
    return sorted(BOARD_REGISTRY.keys())
