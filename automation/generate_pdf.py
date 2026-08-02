#!/usr/bin/env python3
"""HTML → PDF via Playwright (ported from generate-pdf.mjs)."""

from __future__ import annotations

import argparse
import os
import re
import sys

from config import SHORTLISTR_ROOT, OUTPUT_DIR
from paths import FONTS_DIR


def normalize_text_for_ats(html: str) -> tuple[str, dict[str, int]]:
    replacements: dict[str, int] = {}

    def bump(key: str, n: int = 1) -> None:
        replacements[key] = replacements.get(key, 0) + n

    masks: list[str] = []

    def mask_block(match: re.Match) -> str:
        token = f"\x00MASK{len(masks)}\x00"
        masks.append(match.group(0))
        return token

    masked = re.sub(
        r"<(style|script)\b[^>]*>[\s\S]*?</\1>",
        mask_block,
        html,
        flags=re.I,
    )

    def sanitize_text(text: str) -> str:
        if not text:
            return text
        t = text
        t = t.replace("\u2014", "-")
        if "\u2014" in text:
            bump("em-dash", text.count("\u2014"))
        subs = [
            ("\u2013", "en-dash", "-"),
            ("\u201c", "smart-double-quote", '"'),
            ("\u201d", "smart-double-quote", '"'),
            ("\u201e", "smart-double-quote", '"'),
            ("\u201f", "smart-double-quote", '"'),
            ("\u2018", "smart-single-quote", "'"),
            ("\u2019", "smart-single-quote", "'"),
            ("\u201a", "smart-single-quote", "'"),
            ("\u201b", "smart-single-quote", "'"),
            ("\u2026", "ellipsis", "..."),
        ]
        for char, key, repl in subs:
            if char in t:
                bump(key, t.count(char))
                t = t.replace(char, repl)
        for zw in ("\u200b", "\u200c", "\u200d", "\u2060", "\ufeff"):
            if zw in t:
                bump("zero-width", t.count(zw))
                t = t.replace(zw, "")
        if "\u00a0" in t:
            bump("nbsp", t.count("\u00a0"))
            t = t.replace("\u00a0", " ")
        return t

    out = []
    i = 0
    while i < len(masked):
        lt = masked.find("<", i)
        if lt == -1:
            out.append(sanitize_text(masked[i:]))
            break
        out.append(sanitize_text(masked[i:lt]))
        gt = masked.find(">", lt)
        if gt == -1:
            out.append(masked[lt:])
            break
        out.append(masked[lt : gt + 1])
        i = gt + 1

    restored = re.sub(
        r"\x00MASK(\d+)\x00",
        lambda m: masks[int(m.group(1))],
        "".join(out),
    )
    return restored, replacements


_DOC_MARGIN = {"top": "0.6in", "right": "0.6in", "bottom": "0.6in", "left": "0.6in"}
_SHEET_MARGIN = {"top": "0", "right": "0", "bottom": "0", "left": "0"}


def _rewrite_font_urls(html: str) -> str:
    fonts_dir = FONTS_DIR if os.path.isdir(FONTS_DIR) else os.path.join(SHORTLISTR_ROOT, "fonts")
    html = html.replace("url('./fonts/", f"url('file://{fonts_dir}/")
    return re.sub(
        r"file://([^'\"]+)\.(woff2?|ttf|otf)['\"]?\)",
        r"file://\1.\2')",
        html,
    )


def _html_to_pdf_bytes(html: str, fmt: str, margin: dict) -> bytes:
    # Playwright launches a driver subprocess; on Windows that requires the Proactor
    # event loop. A server (uvicorn) can leave a Selector loop policy in place, which
    # makes create_subprocess_exec raise NotImplementedError. Force Proactor first.
    if os.name == "nt":
        import asyncio

        try:
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        except Exception:
            pass
    # Font/asset refs are rewritten to absolute file:// URLs before this call,
    # so no base_url is needed (set_content does not accept one anyway).
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_content(html, wait_until="networkidle")
            page.evaluate("() => document.fonts.ready")
            return page.pdf(
                format=fmt,
                print_background=True,
                margin=margin,
                prefer_css_page_size=False,
            )
        finally:
            browser.close()


def generate_pdf_from_html(
    html: str,
    output_path: str,
    fmt: str = "A4",
    *,
    full_sheet: bool = True,
) -> dict:
    """Render an HTML string to PDF via Playwright (no LaTeX/pdflatex needed).

    full_sheet=True suits self-contained A4 documents (e.g. cv.preview output)
    that define their own page box and inner padding — so PDF margins are zero
    and the result matches the on-screen preview (WYSIWYG).
    """
    output_path = os.path.abspath(output_path)
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    html = _rewrite_font_urls(html)
    html, replacements = normalize_text_for_ats(html)
    total = sum(replacements.values())
    if total:
        breakdown = ", ".join(f"{k}={v}" for k, v in replacements.items())
        print(f"ATS normalization: {total} replacements ({breakdown})")

    margin = _SHEET_MARGIN if full_sheet else _DOC_MARGIN
    pdf_bytes = _html_to_pdf_bytes(html, fmt, margin)

    with open(output_path, "wb") as f:
        f.write(pdf_bytes)

    pdf_text = pdf_bytes.decode("latin1", errors="ignore")
    page_count = len(re.findall(r"/Type\s*/Page[^s]", pdf_text))
    print(f"PDF generated: {output_path} ({page_count} pages, {len(pdf_bytes) / 1024:.1f} KB)")
    return {"output_path": output_path, "page_count": page_count, "size": len(pdf_bytes)}


def generate_pdf(input_path: str, output_path: str, fmt: str = "a4") -> dict:
    input_path = os.path.abspath(input_path)
    output_path = os.path.abspath(output_path)
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    html = _rewrite_font_urls(open(input_path, encoding="utf-8").read())
    html, replacements = normalize_text_for_ats(html)
    total = sum(replacements.values())
    if total:
        breakdown = ", ".join(f"{k}={v}" for k, v in replacements.items())
        print(f"ATS normalization: {total} replacements ({breakdown})")

    print(f"Input:  {input_path}")
    print(f"Output: {output_path}")
    print(f"Format: {fmt.upper()}")

    pdf_bytes = _html_to_pdf_bytes(html, fmt, _DOC_MARGIN)

    with open(output_path, "wb") as f:
        f.write(pdf_bytes)

    pdf_text = pdf_bytes.decode("latin1", errors="ignore")
    page_count = len(re.findall(r"/Type\s*/Page[^s]", pdf_text))
    print(f"PDF generated: {output_path}")
    print(f"Pages: {page_count}")
    print(f"Size: {len(pdf_bytes) / 1024:.1f} KB")
    return {"output_path": output_path, "page_count": page_count, "size": len(pdf_bytes)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate ATS PDF from HTML")
    parser.add_argument("input_html")
    parser.add_argument("output_pdf")
    parser.add_argument("--format", default="a4", choices=("a4", "letter"))
    args = parser.parse_args(argv)
    try:
        generate_pdf(args.input_html, args.output_pdf, args.format)
        return 0
    except Exception as e:
        print(f"❌ PDF generation failed: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
