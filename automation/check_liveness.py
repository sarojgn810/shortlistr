#!/usr/bin/env python3
"""Playwright job link liveness checker."""

from __future__ import annotations

import argparse
import sys

from tracker_tools.liveness import check_url_with_playwright


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check if job URLs are still active")
    parser.add_argument("urls", nargs="*", help="URLs to check")
    parser.add_argument("--file", help="File with one URL per line")
    args = parser.parse_args(argv)

    urls = list(args.urls)
    if args.file:
        urls.extend(
            line.strip()
            for line in open(args.file, encoding="utf-8")
            if line.strip() and not line.startswith("#")
        )

    if not urls:
        print("Usage: check-liveness <url1> [url2] ...", file=sys.stderr)
        print("       check-liveness --file urls.txt", file=sys.stderr)
        return 1

    print(f"Checking {len(urls)} URL(s)...\n")

    from playwright.sync_api import sync_playwright

    active = expired = uncertain = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            for url in urls:
                result = check_url_with_playwright(page, url)
                icon = {"active": "✅", "expired": "❌", "uncertain": "⚠️"}.get(
                    result["result"], "?"
                )
                print(f"{icon} {result['result'].ljust(10)} {url}")
                if result["result"] != "active":
                    print(f"           {result['reason']}")
                if result["result"] == "active":
                    active += 1
                elif result["result"] == "expired":
                    expired += 1
                else:
                    uncertain += 1
        finally:
            browser.close()

    print(f"\nResults: {active} active  {expired} expired  {uncertain} uncertain")
    return 1 if expired or uncertain else 0


if __name__ == "__main__":
    sys.exit(main())
