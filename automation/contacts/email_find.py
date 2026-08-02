"""Email permutation + optional paid verification (never auto-send).

Permute first.last@domain patterns for approved / maybe roles only.
Verification uses a user-supplied API key (Hunter-compatible ``email-verifier``
or NeverBounce-style) when configured on Connections — never invents SMTP RCPT
checks from the laptop as the primary path.
"""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import quote

import requests

logger = logging.getLogger(__name__)

_NAME_SPLIT = re.compile(r"[^a-z0-9]+")


def _parts(full_name: str) -> tuple[str, str]:
    toks = [t for t in _NAME_SPLIT.split((full_name or "").strip().lower()) if t]
    if not toks:
        return "", ""
    if len(toks) == 1:
        return toks[0], ""
    return toks[0], toks[-1]


def company_domain_guess(company: str, website: str = "") -> str:
    if website:
        m = re.search(r"https?://(?:www\.)?([^/]+)", website, re.I)
        if m:
            host = m.group(1).lower()
            if host not in ("linkedin.com", "facebook.com", "twitter.com"):
                return host
    slug = re.sub(r"[^a-z0-9]+", "", (company or "").lower())
    if slug:
        return f"{slug}.com"
    return ""


def permute_emails(full_name: str, domain: str, *, limit: int = 8) -> list[str]:
    """Generate common corporate patterns — candidates, not verified addresses."""
    first, last = _parts(full_name)
    domain = (domain or "").strip().lower().lstrip("@")
    if not domain or not first:
        return []
    patterns: list[str] = []
    if last:
        patterns.extend(
            [
                f"{first}.{last}@{domain}",
                f"{first}{last}@{domain}",
                f"{first[0]}{last}@{domain}",
                f"{first}_{last}@{domain}",
                f"{last}.{first}@{domain}",
                f"{first[0]}.{last}@{domain}",
            ]
        )
    patterns.append(f"{first}@{domain}")
    # Dedupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for e in patterns:
        if e not in seen:
            seen.add(e)
            out.append(e)
        if len(out) >= limit:
            break
    return out


def verify_email(email: str, *, api_key: str = "", provider: str = "hunter") -> dict[str, Any]:
    """Best-effort verify. Without a key returns ``status=unverified``."""
    email = (email or "").strip().lower()
    if not email or "@" not in email:
        return {"email": email, "status": "invalid", "score": 0}
    if not api_key:
        return {"email": email, "status": "unverified", "score": None, "note": "No verifier key on Connections"}

    provider = (provider or "hunter").lower()
    try:
        if provider in ("hunter", "hunter.io"):
            url = (
                "https://api.hunter.io/v2/email-verifier"
                f"?email={quote(email)}&api_key={quote(api_key)}"
            )
            resp = requests.get(url, timeout=15)
            if resp.status_code != 200:
                return {"email": email, "status": "error", "http": resp.status_code}
            data = (resp.json() or {}).get("data") or {}
            status = str(data.get("status") or data.get("result") or "unknown")
            score = data.get("score")
            return {"email": email, "status": status, "score": score, "provider": "hunter"}
        if provider in ("neverbounce", "nb"):
            resp = requests.post(
                "https://api.neverbounce.com/v4/single/check",
                json={"key": api_key, "email": email},
                timeout=15,
            )
            if resp.status_code != 200:
                return {"email": email, "status": "error", "http": resp.status_code}
            data = resp.json() or {}
            return {
                "email": email,
                "status": str(data.get("result") or "unknown"),
                "provider": "neverbounce",
            }
    except Exception as exc:
        logger.warning("email verify failed: %s", exc)
        return {"email": email, "status": "error", "error": str(exc)[:200]}

    return {"email": email, "status": "unverified", "note": f"Unknown provider {provider}"}


def suggest_for_contact(
    name: str,
    company: str,
    *,
    domain: str = "",
    website: str = "",
    verify: bool = False,
    api_key: str = "",
    provider: str = "hunter",
) -> list[dict[str, Any]]:
    dom = domain or company_domain_guess(company, website)
    emails = permute_emails(name, dom)
    out: list[dict[str, Any]] = []
    for e in emails:
        row: dict[str, Any] = {"email": e, "status": "unverified", "source": "permute"}
        if verify and api_key:
            row.update(verify_email(e, api_key=api_key, provider=provider))
            row["source"] = "permute+verify"
        out.append(row)
    return out
