"""Normalize messy job titles (esp. Gmail / Naukri URL slugs) into structured fields.

Deterministic — no LLM. Safe to run on every API enrich and on ingest.
"""

from __future__ import annotations

import re
from typing import Any

_LOCATIONS = (
    "bengaluru",
    "bangalore",
    "hyderabad",
    "pune",
    "mumbai",
    "chennai",
    "delhi",
    "noida",
    "gurgaon",
    "gurugram",
    "kolkata",
    "ahmedabad",
    "remote",
    "india",
    "united states",
    "usa",
    "uk",
    "london",
    "singapore",
    "dubai",
)

_EXP_RE = re.compile(
    r"(?P<a>\d{1,2})\s*(?:to|-|–|—)\s*(?P<b>\d{1,2})\s*(?:years?|yrs?)\b",
    re.I,
)
_EXP_SINGLE_RE = re.compile(
    r"(?P<a>\d{1,2})\s*\+\s*(?:years?|yrs?)\b|(?:min(?:imum)?\s+)?(?P<b>\d{1,2})\s*(?:years?|yrs?)\b",
    re.I,
)
_TRAILING_ID_RE = re.compile(r"(?:\s|-)?(?:\d{8,}|job[-_]?id[-_]?\d+)\s*$", re.I)
_MULTI_SPACE = re.compile(r"\s+")
_SALARY_RE = re.compile(
    r"₹\s*[\d.,]+\s*[lLkK]?|\b\d+(?:\.\d+)?\s*L(?:PA)?\b|\b\d+\s*-\s*\d+\s*LPA\b",
    re.I,
)
# OCR / alert junk: "H .S .R Layout", "B .D"
_DOTTED_FRAG_RE = re.compile(r"\b(?:[A-Za-z]\s*\.\s*){2,}[A-Za-z]?(?:\s+[A-Za-z]+)?\b")
_BAD_COMPANY_RE = re.compile(
    r"^\d+$|^\.|₹|\d+\s*L(?:PA)?\b|^[\d\W_]+$",
    re.I,
)

_ROLE_HINTS = frozenset(
    {
        "engineer",
        "sre",
        "devops",
        "mlops",
        "aiops",
        "platform",
        "reliability",
        "site",
        "cloud",
        "senior",
        "staff",
        "principal",
        "lead",
        "manager",
        "architect",
        "developer",
        "software",
        "backend",
        "frontend",
        "full",
        "stack",
        "kubernetes",
        "docker",
        "aws",
        "azure",
        "gcp",
    }
)


def _norm_spaces(text: str) -> str:
    return _MULTI_SPACE.sub(" ", (text or "").strip())


def extract_experience(text: str) -> tuple[str, str]:
    s = text or ""
    m = _EXP_RE.search(s)
    if m:
        label = f"{m.group('a')}–{m.group('b')} years"
        rest = _norm_spaces(s[: m.start()] + " " + s[m.end() :])
        return label, rest
    m2 = _EXP_SINGLE_RE.search(s)
    if m2:
        n = m2.group("a") or m2.group("b")
        label = f"{n}+ years" if m2.group("a") else f"{n} years"
        rest = _norm_spaces(s[: m2.start()] + " " + s[m2.end() :])
        return label, rest
    return "", s


def extract_locations(text: str) -> tuple[list[str], str]:
    s = text or ""
    found: list[str] = []
    rest = s
    for loc in sorted(_LOCATIONS, key=len, reverse=True):
        pat = re.compile(rf"(?<![a-z0-9]){re.escape(loc)}(?![a-z0-9])", re.I)
        if pat.search(rest):
            display = "Bengaluru" if loc in ("bengaluru", "bangalore") else loc.title()
            if loc == "usa":
                display = "USA"
            elif loc == "uk":
                display = "UK"
            elif loc == "remote":
                display = "Remote"
            if display not in found:
                found.append(display)
            rest = pat.sub(" ", rest)
    return found, _norm_spaces(rest)


def _strip_trailing_id(text: str) -> str:
    return _norm_spaces(_TRAILING_ID_RE.sub("", text or ""))


def _strip_salary_and_noise(text: str) -> str:
    s = _SALARY_RE.sub(" ", text or "")
    s = _DOTTED_FRAG_RE.sub(" ", s)
    return _norm_spaces(s)


def is_plausible_company(name: str) -> bool:
    """Reject job-id / salary / punctuation fragments mistaken for a company."""
    s = (name or "").strip()
    if not s or len(s) < 2:
        return False
    if s.lower() in {"unknown", "untitled", "n/a", "na", "tbd", "?", "company pending"}:
        return False
    if _BAD_COMPANY_RE.search(s):
        return False
    if s.isdigit():
        return False
    return True


def _guess_company_from_tail(tokens: list[str]) -> tuple[str, list[str]]:
    if len(tokens) < 4:
        return "", tokens
    company_parts: list[str] = []
    i = len(tokens) - 1
    while i >= 0 and tokens[i].lower() not in _ROLE_HINTS and len(company_parts) < 3:
        t = tokens[i]
        if t.lower() in {"and", "or", "the", "for", "with"}:
            break
        company_parts.append(t)
        i -= 1
    if not company_parts:
        return "", tokens
    front = tokens[: i + 1]
    if not front or not any(t.lower() in _ROLE_HINTS for t in front):
        return "", tokens
    if len(company_parts) == 1 and len(company_parts[0]) < 3:
        return "", tokens
    company = " ".join(reversed(company_parts)).title()
    if not is_plausible_company(company):
        return "", tokens
    return company, front


def structure_from_blob(
    *,
    title: str = "",
    company: str = "",
    location: str = "",
    experience: str = "",
) -> dict[str, str]:
    """Derive clean title/company/location/experience from messy source text."""
    raw_title = _strip_salary_and_noise(_strip_trailing_id(_norm_spaces(title)))
    raw_company = _norm_spaces(company)
    if not is_plausible_company(raw_company):
        raw_company = ""

    exp = _norm_spaces(experience)
    locs: list[str] = []
    if location:
        locs = [p.strip() for p in re.split(r"[,|/]", location) if p.strip()]

    working = raw_title
    if not exp:
        exp, working = extract_experience(working)
    found_locs, working = extract_locations(working)
    for loc in found_locs:
        if loc not in locs:
            locs.append(loc)

    at_m = re.search(r"\s+(?:at|@|\||–|-)\s+(.+)$", working, re.I)
    guessed_company = ""
    if at_m and not raw_company:
        maybe = _norm_spaces(at_m.group(1))
        maybe = _strip_salary_and_noise(maybe)
        if maybe and maybe.lower() not in {x.lower() for x in _LOCATIONS} and is_plausible_company(
            maybe
        ):
            guessed_company = maybe.title()
            working = _norm_spaces(working[: at_m.start()])

    tokens = [t for t in working.split() if t]
    if not raw_company and not guessed_company and tokens:
        guessed_company, tokens = _guess_company_from_tail(tokens)
        working = " ".join(tokens)

    clean_title = _norm_spaces(working).title()
    clean_title = re.sub(r"\bSre\b", "SRE", clean_title)
    clean_title = re.sub(r"\bMlops\b", "MLOps", clean_title)
    clean_title = re.sub(r"\bAiops\b", "AIOps", clean_title)
    clean_title = re.sub(r"\bAws\b", "AWS", clean_title)
    clean_title = re.sub(r"\bGcp\b", "GCP", clean_title)

    company_out = raw_company or guessed_company
    if not is_plausible_company(company_out):
        company_out = ""

    return {
        "title": clean_title or raw_title.title(),
        "company": company_out,
        "location": ", ".join(locs),
        "experience": exp,
    }


def apply_structure_to_job(job: dict[str, Any]) -> dict[str, Any]:
    """Copy job and fill missing structured fields from a title blob."""
    out = dict(job)
    structured = structure_from_blob(
        title=str(out.get("title") or ""),
        company=str(out.get("company") or ""),
        location=str(out.get("location") or ""),
        experience=str(out.get("experience") or ""),
    )
    cur_title = str(out.get("title") or "")
    if structured["title"] and (
        len(cur_title) > 80
        or re.search(r"\d{8,}", cur_title)
        or (not out.get("company") and structured["company"])
        or len(structured["title"]) < len(cur_title)
    ):
        out["title"] = structured["title"]

    cur_company = str(out.get("company") or "").strip()
    if structured["company"] and (
        not cur_company
        or not is_plausible_company(cur_company)
        or cur_company.lower() in {"unknown", "untitled"}
    ):
        out["company"] = structured["company"]
    elif cur_company and not is_plausible_company(cur_company):
        out["company"] = structured["company"] or ""

    if structured["location"] and not out.get("location"):
        out["location"] = structured["location"]
    if structured["experience"] and not out.get("experience"):
        out["experience"] = structured["experience"]
    return out
