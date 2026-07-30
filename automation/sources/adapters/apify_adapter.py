"""Opt-in Apify source — multi-board actors behind APIFY_TOKEN.

Default off. When enabled and a token is present, runs the configured boards
with the user's target titles/locations and maps results into JobRecords.
Local ATS adapters stay primary for Greenhouse/Lever/Ashby; Apify fills
boards the free APIs miss (Naukri captcha, LinkedIn, Indeed, Dice, …).
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

import config as _cfg
from models.job import JobRecord
from sources.apify_boards import BOARD_REGISTRY, BOARD_SKIPPED, DEFAULT_BOARDS
from sources.apify_client import get_apify_token, run_actor
from sources.base import FetchStats, SourceAdapter, SourceHealth

logger = logging.getLogger(__name__)


def _apify_config() -> dict[str, Any]:
    cfg = getattr(_cfg, "APIFY_SOURCE_CONFIG", None)
    return cfg if isinstance(cfg, dict) else {}


def _experience_years(cfg: dict[str, Any]) -> int:
    if cfg.get("experience") is not None:
        try:
            return int(cfg["experience"])
        except (TypeError, ValueError):
            pass
    cand = getattr(_cfg, "CANDIDATE", None) or {}
    try:
        return int(cand.get("years_exp") or 5)
    except (TypeError, ValueError):
        return 5


def _titles() -> list[str]:
    # One term per role family, so a capped pair budget searches MLOps and
    # AIOps too instead of five seniority variants of the first title.
    picker = getattr(_cfg, "search_titles", None)
    if callable(picker):
        return picker(5)
    return [kw for kw in (getattr(_cfg, "SEARCH_KEYWORDS", None) or []) if len(str(kw)) > 2][:5]


def _locations() -> list[str]:
    picker = getattr(_cfg, "search_locations", None)
    if callable(picker):
        return picker(3) or ["Bengaluru"]
    remote = {"remote", "anywhere", "worldwide", "global", "work from home", "wfh"}
    locs = [kw for kw in (getattr(_cfg, "LOCATION_KEYWORDS", None) or []) if kw.lower() not in remote]
    preferred = [l for l in locs if l not in {"blr", "hyd", "pnq"}]
    return (preferred or locs)[:3] or ["Bengaluru"]


def _as_text(value: Any) -> str:
    """Flatten Apify field shapes (string | list | {name/label/text/full/city})."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, dict):
        for key in (
            "name",
            "label",
            "text",
            "full",
            "short",
            "title",
            "display",
            "value",
            "city",
        ):
            nested = value.get(key)
            if nested is not None and not isinstance(nested, (dict, list)):
                s = str(nested).strip()
                if s:
                    return s
        # Indeed location: city + admin1Code
        city = value.get("city")
        admin = value.get("admin1Code") or value.get("countryName")
        if city:
            parts = [str(city)]
            if admin:
                parts.append(str(admin))
            return ", ".join(parts)
        return ""
    if isinstance(value, (list, tuple)):
        parts: list[str] = []
        for item in value:
            s = _as_text(item)
            if s:
                parts.append(s)
            if len(parts) >= 3:
                break
        return ", ".join(parts)
    return str(value).strip()


def _first(*values: Any) -> str:
    for v in values:
        s = _as_text(v)
        if s:
            return s
    return ""


def _skills_list(raw: Any) -> list[str]:
    if isinstance(raw, str):
        return [s.strip() for s in raw.replace("|", ",").split(",") if s.strip()][:40]
    if isinstance(raw, dict):
        # Naukri: {preferred, other}; Indeed attributes: {code: "Python", ...}
        merged: list[Any] = []
        for key in ("preferred", "other", "mandatory", "skills", "label"):
            val = raw.get(key)
            if isinstance(val, list):
                merged.extend(val)
            elif isinstance(val, str) and val.strip():
                merged.append(val)
        if not merged:
            # Treat dict values as skill labels (Indeed attributes map).
            for val in raw.values():
                if isinstance(val, list):
                    merged.extend(val)
                elif isinstance(val, str) and val.strip() and len(val) < 40:
                    merged.append(val)
        return _skills_list(merged)
    if isinstance(raw, list):
        out: list[str] = []
        for item in raw:
            if isinstance(item, dict):
                s = _as_text(item.get("skill") or item.get("label") or item.get("name") or item)
            else:
                s = _as_text(item)
            if s and s not in out:
                out.append(s)
        return out[:40]
    return []


def _salary_from_item(item: dict) -> str:
    salary = _first(
        item.get("salary"),
        item.get("salaryLabel"),
        item.get("compensation"),
        item.get("salaryDetail"),
        item.get("budget"),
    )
    if salary.lower() in ("not disclosed", "not disclosed.", "unpaid"):
        salary = ""
    if salary:
        return salary
    # Glassdoor / ZipRecruiter style min/max
    lo = item.get("salary_min") or item.get("min_amount") or item.get("minSalary")
    hi = item.get("salary_max") or item.get("max_amount") or item.get("maxSalary")
    if lo or hi:
        cur = item.get("currency") or item.get("salary_currency") or ""
        span = f"{lo or '?'}-{hi or '?'}"
        return f"{cur} {span}".strip()
    # Indeed: baseSalary {min, max, currencyCode, unitOfWork}
    base = item.get("baseSalary")
    if isinstance(base, dict):
        lo, hi = base.get("min"), base.get("max")
        cur = base.get("currencyCode") or ""
        unit = (base.get("unitOfWork") or "").lower()
        if lo or hi:
            span = f"{lo or '?'}-{hi or '?'}"
            if cur:
                span = f"{cur} {span}"
            if unit:
                span = f"{span}/{unit}"
            return span
    return ""


def _item_to_record(item: dict, *, source: str) -> JobRecord | None:
    # Monster (bebity): nested schema.org JobPosting under jobPosting.
    posting = item.get("jobPosting")
    if isinstance(posting, dict):
        flat = dict(item)
        flat.setdefault("title", posting.get("title"))
        flat.setdefault("url", posting.get("url"))
        flat.setdefault("description", posting.get("description"))
        org = posting.get("hiringOrganization")
        if isinstance(org, dict):
            flat.setdefault("company", org.get("name"))
        locs = posting.get("jobLocation")
        if isinstance(locs, list) and locs:
            addr = locs[0].get("address") if isinstance(locs[0], dict) else None
            if isinstance(addr, dict):
                flat.setdefault(
                    "location",
                    ", ".join(
                        p
                        for p in (
                            addr.get("addressLocality"),
                            addr.get("addressRegion"),
                            addr.get("addressCountry"),
                        )
                        if p
                    ),
                )
        item = flat

    url = _first(
        item.get("url"),
        item.get("jobUrl"),
        item.get("link"),
        item.get("applyUrl"),
        item.get("jdURL"),
        item.get("job_url"),
    )
    # Hacker News posts sometimes only have a text body + story link
    if not url.startswith("http"):
        text = _first(item.get("text"), item.get("body"), item.get("description"))
        if source == "Hacker News" and text:
            # Synthetic URL so the row is actionable / dedupable.
            from models.job import job_id_from_url

            fake = f"https://news.ycombinator.com/item?id={item.get('id') or item.get('objectID') or job_id_from_url(text[:80])}"
            url = fake
        else:
            return None
    title = _first(
        item.get("title"),
        item.get("jobTitle"),
        item.get("position"),
        item.get("role"),
        item.get("companyLine"),  # HN
    )
    company = _first(
        item.get("company"),
        item.get("companyName"),
        item.get("company_name"),
        item.get("employer"),
    )
    location = _first(
        item.get("location"),
        item.get("jobLocation"),
        item.get("locations"),
        item.get("place"),
    )
    salary = _salary_from_item(item)
    jd = _first(
        item.get("description"),
        item.get("jobDescription"),
        item.get("jd_text"),
        item.get("snippet"),
        item.get("jobDescriptionHTML"),
        item.get("description_text"),
        item.get("text"),
        item.get("body"),
    )
    if "<" in jd:
        jd = re.sub(r"<br\s*/?>", "\n", jd, flags=re.I)
        jd = re.sub(r"<[^>]+>", "", jd)
    skills = _skills_list(
        item.get("skills")
        or item.get("tagsAndSkills")
        or item.get("keySkills")
        or item.get("attributes")
        or []
    )
    experience = _first(
        item.get("experience"),
        item.get("experienceText"),
        item.get("seniority"),
        item.get("experience_level"),
    )
    if not title and jd:
        title = jd.split("\n", 1)[0][:120]
    if not title:
        return None
    return JobRecord(
        url=url,
        source=source,
        company=company,
        title=title,
        location=location,
        jd_text=jd[:4000] if jd else "",
        salary=salary,
        notes=f"Apify:{source}",
        metadata={
            "skills": skills,
            "experience": experience,
            "apify": True,
            "apify_board": source.lower().replace(" ", ""),
            "raw_keys": sorted(item.keys())[:30],
        },
    )


class ApifyAdapter(SourceAdapter):
    name = "apify"

    def health_check(self) -> SourceHealth:
        if not get_apify_token():
            return SourceHealth(self.name, False, "APIFY_TOKEN not set")
        return SourceHealth(self.name, True, "token present")

    def fetch_raw(self, log_totals: bool = False) -> tuple[list[JobRecord], FetchStats]:
        stats = FetchStats(source=self.name)
        t0 = time.monotonic()
        token = get_apify_token()
        if not token:
            logger.info("Apify skipped: no APIFY_TOKEN")
            stats.duration_ms = int((time.monotonic() - t0) * 1000)
            return [], stats

        cfg = _apify_config()
        raw_boards = [str(b).lower().strip() for b in (cfg.get("boards") or DEFAULT_BOARDS)]
        boards = [b for b in raw_boards if b in BOARD_REGISTRY]
        for b in raw_boards:
            if b in BOARD_SKIPPED:
                logger.info("Apify board '%s' skipped: %s", b, BOARD_SKIPPED[b])
            elif b not in BOARD_REGISTRY and b not in BOARD_SKIPPED:
                logger.warning("Apify board '%s' unknown — known: %s", b, ", ".join(BOARD_REGISTRY))

        timeout = int(cfg.get("timeout_secs") or 180)
        limit = int(cfg.get("limit") or 40)
        titles = _titles()
        locations = _locations()
        if not titles or not boards:
            logger.info("Apify skipped: no titles or no valid boards")
            stats.duration_ms = int((time.monotonic() - t0) * 1000)
            return [], stats

        # Credit + wall-time guard: many boards × 180s each blocks Discover for
        # 20+ minutes. Cap per-board wait when the user enabled a broad set.
        if len(boards) > 3:
            timeout = min(timeout, 90)
        if len(boards) > 6:
            timeout = min(timeout, 60)
        # Credit guard: many boards × many title/loc pairs burns free credit fast.
        # Default 1 pair when >3 boards, else up to 2.
        max_pairs = cfg.get("max_pairs")
        if max_pairs is None:
            max_pairs = 1 if len(boards) > 3 else 2
        max_pairs = max(1, int(max_pairs))
        # Location-major so a tight pair budget covers every role family in the
        # primary city before spending anything on a second city.
        pair_pool: list[tuple[str, str]] = [
            (title, loc) for loc in (locations or ["Remote"]) for title in titles
        ][:12]

        wants_remote = bool(getattr(_cfg, "WANTS_REMOTE", True))
        experience = _experience_years(cfg)
        jobs: list[JobRecord] = []
        seen: set[str] = set()

        # Each board starts at a different point in the pool, so max_pairs=1
        # still covers SRE + MLOps + AIOps across a scan instead of running the
        # same single query on every board.
        for board_index, board_id in enumerate(boards):
            spec = BOARD_REGISTRY[board_id]
            actor = str(cfg.get(f"{board_id}_actor") or spec["actor"])
            label = str(spec["label"])
            build_input = spec["input"]
            offset = (board_index * max_pairs) % len(pair_pool)
            pairs = [pair_pool[(offset + i) % len(pair_pool)] for i in range(min(max_pairs, len(pair_pool)))]
            for title, loc in pairs:
                try:
                    run_input = build_input(
                        title,
                        loc,
                        limit=limit,
                        experience=experience,
                        wants_remote=wants_remote,
                        cfg=cfg,
                    )
                    items = run_actor(
                        actor,
                        run_input,
                        token=token,
                        timeout_secs=timeout,
                    )
                    stats.raw_count += len(items)
                    for item in items:
                        if not isinstance(item, dict):
                            continue
                        rec = _item_to_record(item, source=label)
                        if not rec or rec.job_id in seen:
                            continue
                        seen.add(rec.job_id)
                        jobs.append(rec)
                except Exception as e:
                    logger.warning("Apify %s (%s / %s) failed: %s", label, title, loc, e)
                    stats.error = str(e)

        stats.duration_ms = int((time.monotonic() - t0) * 1000)
        if log_totals:
            logger.info(
                "Apify: boards=%s pairs/board=%d of pool=%s raw=%d → %d records (%dms)",
                boards,
                min(max_pairs, len(pair_pool)),
                [t for t, _ in pair_pool],
                stats.raw_count,
                len(jobs),
                stats.duration_ms,
            )
        return jobs, stats
