"""Email pattern learning + permutation (Stages 3–4)."""

from __future__ import annotations

from collections import Counter
from typing import Any

PATTERNS = (
    "{first}.{last}",
    "{f}{last}",
    "{first}{last}",
    "{first}_{last}",
    "{first}",
    "{last}.{first}",
    "{f}.{last}",
)


def _split_name(full_name: str) -> tuple[str, str]:
    parts = [p for p in (full_name or "").strip().split() if p]
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0].lower(), ""
    return parts[0].lower(), parts[-1].lower()


def apply_pattern(pattern: str, first: str, last: str) -> str:
    f, l = (first or "").lower(), (last or "").lower()
    # Patterns that need a last name must not emit trailing dots / underscores.
    if ("{last}" in pattern or "{l}" in pattern) and not l:
        return ""
    try:
        local = pattern.format(first=f, last=l, f=f[:1] if f else "", l=l[:1] if l else "")
    except Exception:
        return ""
    local = (local or "").strip().lower()
    if not local or local.startswith(".") or local.endswith(".") or ".." in local:
        return ""
    if local.startswith("_") or local.endswith("_"):
        return ""
    return local


def learn_pattern(
    known: list[tuple[str, str, str]],
) -> tuple[str | None, float, int]:
    """known = [(first, last, email), ...]. Returns (pattern, confidence, samples)."""
    votes: Counter[str] = Counter()
    for first, last, email in known:
        local = (email or "").split("@")[0].lower()
        if not local or not first:
            continue
        for p in PATTERNS:
            if apply_pattern(p, first, last) == local:
                votes[p] += 1
                break
    if not votes:
        return None, 0.0, 0
    top, n = votes.most_common(1)[0]
    total = sum(votes.values())
    return top, n / total, total


def generate_emails(
    first: str,
    last: str,
    domain: str,
    *,
    pattern: str | None = None,
    limit: int = 8,
) -> list[tuple[str, str, float]]:
    """Return [(email, method, pattern_conf), ...]."""
    domain = (domain or "").strip().lower().lstrip("@")
    first, last = (first or "").lower(), (last or "").lower()
    if not domain or not first:
        return []
    # Single-token "names" (GitHub logins, company slugs) must not be permuted.
    if not last:
        return []
    out: list[tuple[str, str, float]] = []
    seen: set[str] = set()
    if pattern:
        local = apply_pattern(pattern, first, last)
        if local:
            e = f"{local}@{domain}"
            out.append((e, "pattern", 0.85))
            seen.add(e)
    for p in PATTERNS:
        local = apply_pattern(p, first, last)
        if not local:
            continue
        e = f"{local}@{domain}"
        if e in seen:
            continue
        seen.add(e)
        conf = 0.4 if not pattern else 0.55
        out.append((e, f"permute:{p}", conf))
        if len(out) >= limit:
            break
    return out


def pairs_from_known_emails(
    emails: list[str],
    names: list[str],
) -> list[tuple[str, str, str]]:
    """Match known emails to name parts when local-part contains first/last."""
    pairs: list[tuple[str, str, str]] = []
    for name in names:
        first, last = _split_name(name)
        if not first:
            continue
        for email in emails:
            local = email.split("@")[0].lower()
            if first in local and (not last or last in local or first[0] + last in local):
                pairs.append((first, last, email.lower()))
    return pairs
