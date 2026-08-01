"""Company → email domain + MX fingerprint (Stage 1)."""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

_HOST_RE = re.compile(r"https?://(?:www\.)?([^/\s\"']+)", re.I)


def normalize_host(host: str) -> str:
    h = (host or "").strip().lower()
    h = h.split("@")[-1]
    h = re.sub(r"^https?://", "", h)
    h = h.split("/")[0].split("?")[0]
    if h.startswith("www."):
        h = h[4:]
    # Drop known non-email hosts
    if h in ("linkedin.com", "facebook.com", "twitter.com", "x.com", "github.com"):
        return ""
    return h


def host_from_url(url: str) -> str:
    m = _HOST_RE.search(url or "")
    return normalize_host(m.group(1) if m else "")


def domain_from_ats_json(metadata: dict[str, Any] | None) -> str:
    """Best-effort website from ATS raw / schema.org-ish metadata."""
    if not metadata or not isinstance(metadata, dict):
        return ""
    for key in ("website", "company_url", "organization_url", "sameAs", "url"):
        v = metadata.get(key)
        if isinstance(v, str) and v.startswith("http"):
            h = host_from_url(v)
            if h:
                return h
    org = metadata.get("hiringOrganization") or metadata.get("organization")
    if isinstance(org, dict):
        for key in ("sameAs", "url", "website"):
            v = org.get(key)
            if isinstance(v, list) and v:
                v = v[0]
            if isinstance(v, str):
                h = host_from_url(v) if "://" in v else normalize_host(v)
                if h:
                    return h
    return ""


def autocomplete_domain(company_name: str, *, timeout: float = 8.0) -> str | None:
    """Clearbit Autocomplete (free, no key) — best-effort name → domain."""
    q = (company_name or "").strip()
    if len(q) < 2:
        return None
    try:
        resp = requests.get(
            "https://autocomplete.clearbit.com/v1/companies/suggest",
            params={"query": q},
            timeout=timeout,
            headers={"User-Agent": "AutojobContactResolve/1.0"},
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        if not isinstance(data, list) or not data:
            return None
        top = data[0] if isinstance(data[0], dict) else {}
        dom = normalize_host(str(top.get("domain") or ""))
        return dom or None
    except Exception as exc:
        logger.debug("clearbit autocomplete failed: %s", exc)
        return None


def mx_lookup(domain: str) -> tuple[str, list[str]]:
    """Return (mx_provider, mx_hosts). Uses dnspython if present, else empty."""
    domain = normalize_host(domain)
    if not domain:
        return "unknown", []
    hosts: list[str] = []
    try:
        import dns.resolver  # type: ignore

        answers = dns.resolver.resolve(domain, "MX", lifetime=5)
        for r in answers:
            hosts.append(str(r.exchange).rstrip(".").lower())
    except Exception:
        # Fallback: try socket getaddrinfo is useless for MX; leave unknown.
        return "unknown", []

    joined = " ".join(hosts)
    if "pphosted.com" in joined or "ppe-hosted" in joined or "proofpoint" in joined:
        return "proofpoint", hosts
    if "mimecast" in joined:
        return "mimecast", hosts
    if "google.com" in joined or "googlemail.com" in joined or "aspmx.l.google" in joined:
        return "google", hosts
    if "protection.outlook.com" in joined or "mail.protection.outlook" in joined:
        return "microsoft365", hosts
    if hosts:
        return "other", hosts
    return "unknown", []


def guess_catch_all(mx_provider: str) -> int | None:
    """SEG gateways often accept-all — flag risk without SMTP RCPT."""
    if mx_provider in ("proofpoint", "mimecast"):
        return 1
    return None


def resolve_company_domain(
    company_name: str,
    *,
    website: str = "",
    apply_url: str = "",
    metadata: dict[str, Any] | None = None,
    use_autocomplete: bool = True,
) -> dict[str, Any]:
    """Ladder: ATS metadata → website → apply host → autocomplete → slug.com guess."""
    candidates: list[tuple[str, str]] = []  # (domain, source)
    ats = domain_from_ats_json(metadata)
    if ats:
        candidates.append((ats, "ats_metadata"))
    if website:
        h = host_from_url(website) if "://" in website else normalize_host(website)
        if h:
            candidates.append((h, "website"))
    apply_host = host_from_url(apply_url)
    # Skip ATS board hosts as email domains
    ats_boards = (
        "greenhouse.io",
        "lever.co",
        "ashbyhq.com",
        "myworkdayjobs.com",
        "smartrecruiters.com",
        "recruitee.com",
        "teamtailor.com",
        "workable.com",
        "linkedin.com",
        "naukri.com",
    )
    if apply_host and not any(apply_host.endswith(b) for b in ats_boards):
        candidates.append((apply_host, "apply_url"))

    if use_autocomplete:
        auto = autocomplete_domain(company_name)
        if auto:
            candidates.append((auto, "clearbit_autocomplete"))

    slug = re.sub(r"[^a-z0-9]+", "", (company_name or "").lower())
    if slug:
        candidates.append((f"{slug}.com", "slug_guess"))

    chosen = ""
    source = ""
    mx_provider = "unknown"
    mx_hosts: list[str] = []
    for dom, src in candidates:
        if not dom:
            continue
        # Prefer first candidate that has MX when resolvable
        provider, hosts = mx_lookup(dom)
        if provider != "unknown" or src != "slug_guess":
            chosen, source = dom, src
            mx_provider, mx_hosts = provider, hosts
            if provider != "unknown":
                break
            # Keep searching for one with MX
            continue
    if not chosen and candidates:
        chosen, source = candidates[0]

    return {
        "email_domain": chosen,
        "website_domain": chosen,
        "domain_source": source,
        "mx_provider": mx_provider,
        "mx_hosts": mx_hosts,
        "is_catch_all": guess_catch_all(mx_provider),
        "candidates": [{"domain": d, "source": s} for d, s in candidates[:6]],
    }
