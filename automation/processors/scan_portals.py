#!/usr/bin/env python3
"""Zero-token portal scanner (ported from scan.mjs)."""

from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import date

import requests
import yaml

from config import SHORTLISTR_ROOT, PIPELINE_PATH
from paths import PORTALS_PATH, SCAN_HISTORY_PATH, applications_file
from processors.search_discovery import discover_from_search, search_backend_available

CONCURRENCY = 10  # reserved for future parallel fetch
FETCH_TIMEOUT = 10


def detect_api(company: dict) -> dict | None:
    api = company.get("api") or ""
    if api and "greenhouse" in api:
        return {"type": "greenhouse", "url": api}

    url = company.get("careers_url") or ""

    m = re.search(r"jobs\.ashbyhq\.com/([^/?#]+)", url)
    if m:
        return {
            "type": "ashby",
            "url": f"https://api.ashbyhq.com/posting-api/job-board/{m.group(1)}?includeCompensation=true",
        }

    m = re.search(r"jobs\.lever\.co/([^/?#]+)", url)
    if m:
        return {"type": "lever", "url": f"https://api.lever.co/v0/postings/{m.group(1)}"}

    m = re.search(r"job-boards(?:\.eu)?\.greenhouse\.io/([^/?#]+)", url)
    if m and not company.get("api"):
        return {
            "type": "greenhouse",
            "url": f"https://boards-api.greenhouse.io/v1/boards/{m.group(1)}/jobs",
        }
    return None


def parse_greenhouse(data: dict, company_name: str) -> list[dict]:
    return [
        {
            "title": j.get("title", ""),
            "url": j.get("absolute_url", ""),
            "company": company_name,
            "location": (j.get("location") or {}).get("name", ""),
        }
        for j in data.get("jobs", [])
    ]


def parse_ashby(data: dict, company_name: str) -> list[dict]:
    return [
        {
            "title": j.get("title", ""),
            "url": j.get("jobUrl", ""),
            "company": company_name,
            "location": j.get("location", ""),
        }
        for j in data.get("jobs", [])
    ]


def parse_lever(data, company_name: str) -> list[dict]:
    if not isinstance(data, list):
        return []
    return [
        {
            "title": j.get("text", ""),
            "url": j.get("hostedUrl", ""),
            "company": company_name,
            "location": (j.get("categories") or {}).get("location", ""),
        }
        for j in data
    ]


PARSERS = {"greenhouse": parse_greenhouse, "ashby": parse_ashby, "lever": parse_lever}


def build_title_filter(title_filter: dict | None) -> callable:
    positive = [k.lower() for k in (title_filter or {}).get("positive", [])]
    negative = [k.lower() for k in (title_filter or {}).get("negative", [])]

    def matches(title: str) -> bool:
        lower = title.lower()
        has_positive = not positive or any(k in lower for k in positive)
        has_negative = any(k in lower for k in negative)
        return has_positive and not has_negative

    return matches


def load_seen_urls() -> set[str]:
    seen: set[str] = set()
    if os.path.exists(SCAN_HISTORY_PATH):
        for line in open(SCAN_HISTORY_PATH, encoding="utf-8").read().split("\n")[1:]:
            url = line.split("\t")[0]
            if url:
                seen.add(url)
    if os.path.exists(PIPELINE_PATH):
        text = open(PIPELINE_PATH, encoding="utf-8").read()
        for m in re.finditer(r"- \[[ x]\] (https?://\S+)", text):
            seen.add(m.group(1))
    apps = applications_file()
    if os.path.exists(apps):
        text = open(apps, encoding="utf-8").read()
        for m in re.finditer(r"https?://[^\s|)]+", text):
            seen.add(m.group(0))
    return seen


def load_seen_company_roles() -> set[str]:
    seen: set[str] = set()
    apps = applications_file()
    if os.path.exists(apps):
        text = open(apps, encoding="utf-8").read()
        for m in re.finditer(r"\|[^|]+\|[^|]+\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|", text):
            company, role = m.group(1).strip().lower(), m.group(2).strip().lower()
            if company and role and company != "company":
                seen.add(f"{company}::{role}")
    return seen


def find_section_marker(text: str, markers: list[str], fallback: str) -> str:
    for m in markers:
        if m in text:
            return m
    return fallback


def append_to_pipeline(offers: list[dict]) -> None:
    if not offers:
        return
    text = open(PIPELINE_PATH, encoding="utf-8").read()
    pending_markers = ["## Pending", "## Pendientes"]
    processed_markers = ["## Processed", "## Procesadas"]
    marker = find_section_marker(text, pending_markers, "## Pending")
    idx = text.find(marker)
    block = "\n".join(f"- [ ] {o['url']} | {o['company']} | {o['title']}" for o in offers)

    if idx == -1:
        proc_marker = find_section_marker(text, processed_markers, "## Processed")
        proc_idx = text.find(proc_marker)
        insert_at = proc_idx if proc_idx != -1 else len(text)
        text = text[:insert_at] + f"\n## Pending\n\n{block}\n\n" + text[insert_at:]
    else:
        after = idx + len(marker)
        next_section = text.find("\n## ", after)
        insert_at = next_section if next_section != -1 else len(text)
        text = text[:insert_at] + "\n" + block + "\n" + text[insert_at:]

    with open(PIPELINE_PATH, "w", encoding="utf-8") as f:
        f.write(text)


def append_to_scan_history(offers: list[dict], day: str) -> None:
    if not os.path.exists(SCAN_HISTORY_PATH):
        with open(SCAN_HISTORY_PATH, "w", encoding="utf-8") as f:
            f.write("url\tfirst_seen\tportal\ttitle\tcompany\tstatus\n")
    lines = "\n".join(
        f"{o['url']}\t{day}\t{o['source']}\t{o['title']}\t{o['company']}\tadded"
        for o in offers
    ) + "\n"
    with open(SCAN_HISTORY_PATH, "a", encoding="utf-8") as f:
        f.write(lines)


def fetch_json(url: str) -> dict | list:
    resp = requests.get(url, timeout=FETCH_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scan job portals via ATS APIs")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--company", help="Filter to a single company name")
    args = parser.parse_args(argv)

    os.makedirs(os.path.join(SHORTLISTR_ROOT, "data"), exist_ok=True)

    if not os.path.exists(PORTALS_PATH):
        print("Error: portals.yml not found. Run onboarding first.", file=sys.stderr)
        return 1

    config = yaml.safe_load(open(PORTALS_PATH, encoding="utf-8")) or {}
    companies = config.get("tracked_companies") or []
    title_filter = build_title_filter(config.get("title_filter"))

    targets = []
    for c in companies:
        if c.get("enabled") is False:
            continue
        if args.company and args.company.lower() not in c.get("name", "").lower():
            continue
        api = detect_api(c)
        if api:
            targets.append({**c, "_api": api})

    enabled = [c for c in companies if c.get("enabled") is not False]
    skipped = len(enabled) - len(targets)
    print(f"Scanning {len(targets)} companies via API ({skipped} skipped — no API detected)")
    if args.dry_run:
        print("(dry run — no files will be written)\n")

    seen_urls = load_seen_urls()
    seen_roles = load_seen_company_roles()
    today = date.today().isoformat()
    total_found = total_filtered = total_dupes = 0
    new_offers: list[dict] = []
    errors: list[tuple[str, str]] = []

    for company in targets:
        api = company["_api"]
        try:
            data = fetch_json(api["url"])
            jobs = PARSERS[api["type"]](data, company["name"])
            total_found += len(jobs)
            for job in jobs:
                if not title_filter(job["title"]):
                    total_filtered += 1
                    continue
                if job["url"] in seen_urls:
                    total_dupes += 1
                    continue
                key = f"{job['company'].lower()}::{job['title'].lower()}"
                if key in seen_roles:
                    total_dupes += 1
                    continue
                seen_urls.add(job["url"])
                seen_roles.add(key)
                new_offers.append({**job, "source": f"{api['type']}-api"})
        except Exception as e:
            errors.append((company["name"], str(e)))

    # Level 3 — search_queries (cross-company keyword discovery)
    search_stats: dict = {}
    search_queries = config.get("search_queries") or []
    enabled_queries = [q for q in search_queries if isinstance(q, dict) and q.get("enabled", True)]
    if enabled_queries:
        backend = search_backend_available()
        print(
            f"\nLevel 3 search: {len(enabled_queries)} queries "
            f"(backend: {backend or 'duckduckgo'})"
        )
        search_offers, search_stats = discover_from_search(
            title_filter=title_filter,
            check_liveness=True,
        )
        for job in search_offers:
            url = job.get("url", "")
            if not url or url in seen_urls:
                total_dupes += 1
                continue
            key = f"{job['company'].lower()}::{job['title'].lower()}"
            if key in seen_roles:
                total_dupes += 1
                continue
            seen_urls.add(url)
            seen_roles.add(key)
            new_offers.append(job)
        total_found += search_stats.get("resolved", 0) + search_stats.get("title_filtered", 0)
        total_filtered += search_stats.get("title_filtered", 0)

    if not args.dry_run and new_offers:
        append_to_pipeline(new_offers)
        append_to_scan_history(new_offers, today)

    print(f"\n{'━' * 45}")
    print(f"Portal Scan — {today}")
    print(f"{'━' * 45}")
    print(f"Companies scanned:     {len(targets)}")
    print(f"Total jobs found:      {total_found}")
    print(f"Filtered by title:     {total_filtered} removed")
    print(f"Duplicates:            {total_dupes} skipped")
    print(f"New offers added:      {len(new_offers)}")

    if search_stats:
        print(f"\nLevel 3 search stats:")
        print(f"  Queries run:         {search_stats.get('queries_run', 0)}")
        print(f"  ATS URLs found:      {search_stats.get('ats_urls', 0)}")
        print(f"  Resolved via API:    {search_stats.get('resolved', 0)}")
        print(f"  Expired (skipped):   {search_stats.get('liveness_expired', 0)}")

    if errors:
        print(f"\nErrors ({len(errors)}):")
        for name, err in errors:
            print(f"  ✗ {name}: {err}")

    if new_offers:
        print("\nNew offers:")
        for o in new_offers:
            print(f"  + {o['company']} | {o['title']} | {o.get('location') or 'N/A'}")
        if args.dry_run:
            print("\n(dry run — run without --dry-run to save results)")
        else:
            print(f"\nResults saved to {PIPELINE_PATH} and {SCAN_HISTORY_PATH}")

    print("\n→ Run /shortlistr inbox to evaluate new offers.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
