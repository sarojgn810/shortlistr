"""Job posting liveness classification (ported from liveness-core.mjs)."""

from __future__ import annotations

import re
from typing import Any

HARD_EXPIRED_PATTERNS = [
    re.compile(r"job (is )?no longer available", re.I),
    re.compile(r"job.*no longer open", re.I),
    re.compile(r"position has been filled", re.I),
    re.compile(r"this job has expired", re.I),
    re.compile(r"job posting has expired", re.I),
    re.compile(r"no longer accepting applications", re.I),
    re.compile(r"this (position|role|job) (is )?no longer", re.I),
    re.compile(r"this job (listing )?is closed", re.I),
    re.compile(r"job (listing )?not found", re.I),
    re.compile(r"the page you are looking for doesn.t exist", re.I),
    re.compile(r"diese stelle (ist )?(nicht mehr|bereits) besetzt", re.I),
    re.compile(r"offre (expirée|n'est plus disponible)", re.I),
]

LISTING_PAGE_PATTERNS = [
    re.compile(r"\d+\s+jobs?\s+found", re.I),
    re.compile(r"search for jobs page is loaded", re.I),
]

EXPIRED_URL_PATTERNS = [re.compile(r"[?&]error=true", re.I)]

APPLY_PATTERNS = [
    re.compile(r"\bapply\b", re.I),
    re.compile(r"\bsolicitar\b", re.I),
    re.compile(r"\bbewerben\b", re.I),
    re.compile(r"\bpostuler\b", re.I),
    re.compile(r"submit application", re.I),
    re.compile(r"easy apply", re.I),
    re.compile(r"start application", re.I),
    re.compile(r"ich bewerbe mich", re.I),
]

MIN_CONTENT_CHARS = 300


def _first_match(patterns: list[re.Pattern], text: str = "") -> re.Pattern | None:
    for p in patterns:
        if p.search(text):
            return p
    return None


def _has_apply_control(controls: list[str]) -> bool:
    return any(p.search(c) for c in controls for p in APPLY_PATTERNS)


def classify_liveness(
    *,
    status: int = 0,
    final_url: str = "",
    body_text: str = "",
    apply_controls: list[str] | None = None,
) -> dict[str, str]:
    apply_controls = apply_controls or []

    if status in (404, 410):
        return {"result": "expired", "reason": f"HTTP {status}"}

    expired_url = _first_match(EXPIRED_URL_PATTERNS, final_url)
    if expired_url:
        return {"result": "expired", "reason": f"redirect to {final_url}"}

    expired_body = _first_match(HARD_EXPIRED_PATTERNS, body_text)
    if expired_body:
        return {"result": "expired", "reason": f"pattern matched: {expired_body.pattern}"}

    if _has_apply_control(apply_controls):
        return {"result": "active", "reason": "visible apply control detected"}

    listing_page = _first_match(LISTING_PAGE_PATTERNS, body_text)
    if listing_page:
        return {"result": "expired", "reason": f"pattern matched: {listing_page.pattern}"}

    if len(body_text.strip()) < MIN_CONTENT_CHARS:
        return {"result": "expired", "reason": "insufficient content — likely nav/footer only"}

    return {"result": "uncertain", "reason": "content present but no visible apply control found"}


def check_url_with_playwright(page: Any, url: str) -> dict[str, str]:
    """Check a single URL using an existing Playwright page."""
    try:
        response = page.goto(url, wait_until="domcontentloaded", timeout=15000)
        status = response.status if response else 0
        page.wait_for_timeout(2000)
        final_url = page.url
        body_text = page.evaluate("() => document.body?.innerText ?? ''")
        apply_controls = page.evaluate(
            """() => {
              const candidates = Array.from(
                document.querySelectorAll(
                  'a, button, input[type="submit"], input[type="button"], [role="button"]'
                )
              );
              return candidates
                .filter((element) => {
                  if (element.closest('nav, header, footer')) return false;
                  if (element.closest('[aria-hidden="true"]')) return false;
                  const style = window.getComputedStyle(element);
                  if (style.display === 'none' || style.visibility === 'hidden') return false;
                  if (!element.getClientRects().length) return false;
                  return Array.from(element.getClientRects()).some(
                    (rect) => rect.width > 0 && rect.height > 0
                  );
                })
                .map((element) => {
                  const label = [
                    element.innerText,
                    element.value,
                    element.getAttribute('aria-label'),
                    element.getAttribute('title'),
                  ]
                    .filter(Boolean)
                    .join(' ')
                    .replace(/\\s+/g, ' ')
                    .trim();
                  return label;
                })
                .filter(Boolean);
            }"""
        )
        return classify_liveness(
            status=status,
            final_url=final_url,
            body_text=body_text,
            apply_controls=apply_controls,
        )
    except Exception as e:
        msg = str(e).split("\n")[0]
        return {"result": "expired", "reason": f"navigation error: {msg}"}
