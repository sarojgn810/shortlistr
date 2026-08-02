"""Instantly-compatible CSV export for approved outreach contacts.

Never auto-uploads to Instantly — downloads a CSV the user imports themselves.
Columns match Instantly's common lead import: email, first_name, last_name,
company_name, personalization, website, linkedin.
"""

from __future__ import annotations

import csv
import io
import re
from typing import Any

_INSTANTLY_HEADERS = (
    "email",
    "first_name",
    "last_name",
    "company_name",
    "personalization",
    "website",
    "linkedin",
)


def _split_name(name: str) -> tuple[str, str]:
    parts = [p for p in re.split(r"\s+", (name or "").strip()) if p]
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


def rows_from_contacts(
    contacts: list[dict[str, Any]],
    *,
    company: str = "",
    personalization: str = "",
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for c in contacts:
        email = str(c.get("email") or "").strip()
        if not email or "@" not in email:
            continue
        key = email.lower()
        if key in seen:
            continue
        seen.add(key)
        first, last = _split_name(str(c.get("name") or ""))
        rows.append(
            {
                "email": email,
                "first_name": first,
                "last_name": last,
                "company_name": str(c.get("company") or company or "").strip(),
                "personalization": str(
                    c.get("personalization") or personalization or c.get("note") or ""
                ).strip()[:500],
                "website": str(c.get("website") or "").strip(),
                "linkedin": str(c.get("linkedin_url") or c.get("linkedin") or "").strip(),
            }
        )
    return rows


def to_csv(rows: list[dict[str, str]]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(_INSTANTLY_HEADERS), extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({h: row.get(h, "") for h in _INSTANTLY_HEADERS})
    return buf.getvalue()
