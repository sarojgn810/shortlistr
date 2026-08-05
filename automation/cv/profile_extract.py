"""Best-effort extraction of structured profile fields from resume markdown.

Used to pre-fill the onboarding Profile step when a user uploads a résumé. Every
field is heuristic and meant to be reviewed by the user — we only return values
we are reasonably confident about and omit the rest so they never clobber a field
the user already typed.
"""

from __future__ import annotations

import datetime
import re
from typing import Any

from cv.parser import infer_cv_name, parse_cv_markdown

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"(?<!\w)(\+?\d[\d\s\-().]{8,}\d)(?!\w)")
_LINKEDIN_RE = re.compile(r"(?:https?://)?(?:www\.)?linkedin\.com/in/[^\s)|,]+", re.I)
_GITHUB_RE = re.compile(r"(?:https?://)?(?:www\.)?github\.com/[^\s)|,]+", re.I)
_URL_RE = re.compile(r"https?://[^\s)|,]+", re.I)
_YEARS_RE = re.compile(r"(\d{1,2})\+?\s*(?:years?|yrs?)\b", re.I)
# Words that mark a segment as a job title rather than a company name.
_ROLE_WORD_RE = re.compile(
    r"\b(engineer|engineering|developer|analyst|manager|lead|architect|consultant|"
    r"administrator|specialist|tester|sre|devops|scientist|designer|support|"
    r"associate|executive|officer|head|director|intern|programmer|technician)\b",
    re.I,
)
# Segments carrying these are employer names, not job titles.
_CORP_SUFFIX_RE = re.compile(
    r"\b(pvt|private|ltd|limited|inc|llc|llp|plc|gmbh|corp|corporation|technologies|"
    r"technology|solutions|systems|services|consultancy|consulting|labs|software|"
    r"infotech|industries|group|holdings|enterprises|associates)\b", re.I)
_MONTH_RE = re.compile(
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\b", re.I)
_YEAR_TOKEN_RE = re.compile(r"\b(?:19|20)\d{2}\b")
_PRESENT_RE = re.compile(r"\b(present|current|now|till\s*date|todate)\b", re.I)
_SENIORITY_PREFIX_RE = re.compile(
    r"^(senior|sr\.?|lead|principal|staff|junior|jr\.?|associate|assistant)\s+",
    re.I,
)

# A location line looks like "City, Region" / "City, Country" but is not an
# email, URL, or phone number.
_LOCATION_RE = re.compile(
    r"^[A-Za-z][A-Za-z .'-]{1,40},\s*[A-Za-z][A-Za-z .'-]{1,40}$"
)


def _clean_url(url: str) -> str:
    url = url.strip().rstrip(".,;)")
    if not url.lower().startswith("http"):
        url = "https://" + url
    return url


def _first_email(text: str) -> str:
    m = _EMAIL_RE.search(text)
    return m.group(0) if m else ""


def _first_phone(text: str) -> str:
    for m in _PHONE_RE.finditer(text):
        candidate = m.group(1).strip()
        digits = re.sub(r"\D", "", candidate)
        # Avoid matching year ranges / id numbers — real phone numbers have 10-15 digits.
        if 10 <= len(digits) <= 15:
            return candidate
    return ""


def _first(pattern: re.Pattern[str], text: str) -> str:
    m = pattern.search(text)
    return _clean_url(m.group(0)) if m else ""


# Separators seen in résumé contact lines: pipes, bullets, middle dots, slashes.
_CONTACT_SEP_RE = re.compile(r"[|\n•·∙‧/]+")


def _clean_segment(raw: str) -> str:
    # Strip markdown emphasis and surrounding punctuation/space.
    return raw.replace("*", "").replace("_", "").strip(" \t,-–—|·•")


def _extract_location(contact: str) -> str:
    """City from a contact block. "City, Region" first, a bare city second.

    Two passes rather than one, because contact rows are split on "/" among
    other things and a LinkedIn URL leaves fragments — "in", "asha-menon" —
    that sit *earlier* in the row than the real city. Taking the first plausible
    segment therefore picked the fragment. A comma-form location is unambiguous,
    so it wins wherever it appears.
    """
    segments: list[str] = []
    for raw in _CONTACT_SEP_RE.split(contact):
        line = _clean_segment(raw)
        if not line or "@" in line or _URL_RE.search(line):
            continue
        if re.search(r"\d{4,}", line):  # skip phone-ish / postal-code-ish lines
            continue
        segments.append(line)

    for line in segments:
        if _LOCATION_RE.match(line):
            return line
    # A bare city is just as common as "City, Region" — "Bengaluru" on a contact
    # row was dropped for having no comma.
    for line in segments:
        if _single_token_location(line):
            return line
    return ""


def _location_from_contact_row(text: str) -> str:
    """Pull the city out of a one-line contact row.

    Modern one-page résumés put phone, LinkedIn, city and email on a single
    line with icons between them, and PDF extraction yields exactly that with
    no separators to split on — the "/" in the LinkedIn URL was the only split
    point, which produced the fragment "in" as the candidate city.

    Everything identifiable is removed instead: email, URL, then long digit
    runs. Whatever survives is the part that was never one of those.
    """
    for line in (text or "").splitlines()[:15]:
        if "@" not in line and not _URL_RE.search(line):
            continue
        rest = _EMAIL_RE.sub(" ", line)
        rest = _URL_RE.sub(" ", rest)
        # Contact rows write links without a scheme — "linkedin.com/in/name"
        # never matched the http-anchored pattern above and survived as the
        # candidate city.
        rest = re.sub(r"\S*\w\.\w{2,}\S*", " ", rest)
        rest = re.sub(r"\S*/\S*", " ", rest)
        rest = re.sub(r"[\d][\d\s+()\-]{3,}", " ", rest)
        rest = re.sub(r"\s+", " ", rest).strip(" |·•,")
        if rest and _single_token_location(rest):
            return rest
    return ""


# Splitting a contact row on "/" and friends leaves fragments like the "in" from
# linkedin.com/in/name. Short connectives are never a city, and a bare "in" in
# the location field is worse than leaving it blank.
_NOT_A_PLACE = {
    "in", "at", "of", "on", "the", "and", "com", "www", "org", "net", "io",
    "me", "co", "dev", "app", "profile", "resume", "cv", "email", "phone",
    "mobile", "tel", "www.", "linkedin", "github", "portfolio",
}

# Country and region codes people really do write as their whole location.
# Everything else in caps on a CV is a technology, and a skills row sits close
# enough to the contact row to be mistaken for it.
_PLACE_ACRONYMS = {"USA", "US", "UK", "UAE", "EU", "NYC", "SF", "LA", "DC"}


def _is_bare_acronym(line: str) -> bool:
    """True for AWS, GCP, SQL, CI/CD — caps with no lowercase and no comma.

    A real one-word city on a résumé is written in title case: Bangalore,
    London, Pune. "AWS" was being read as the candidate's home city, which then
    seeded preferred_locations and skewed the location score on every job.
    """
    s = line.strip()
    if s.upper() in _PLACE_ACRONYMS:
        return False
    letters = [c for c in s if c.isalpha()]
    return bool(letters) and all(c.isupper() for c in letters) and len(s) <= 6


def _single_token_location(line: str) -> bool:
    words = line.split()
    if "," in line or not 1 <= len(words) <= 3:
        return False
    # "UK" is two characters and a real answer, so the length floor lets the
    # known country codes past.
    if line.strip().upper() not in _PLACE_ACRONYMS and len(line) < 3:
        return False
    if line.strip().lower() in _NOT_A_PLACE:
        return False
    if _is_bare_acronym(line):
        return False
    # A dot with no space after it is a domain, not an abbreviation:
    # "linkedin.com" is out, "St. Louis" stays in. Without this the domain won
    # because it appears earlier in the contact row than the city does.
    if re.search(r"\.\S", line):
        return False
    if any(w.lower() in _NOT_A_PLACE for w in words):
        return False
    try:
        from linkedin_optimizer.parser import looks_like_location
    except Exception:
        return False
    return looks_like_location(line)


def _extract_years_exp(md: str, summary: str, experience: str) -> int:
    # Prefer an explicit "N years" claim in the summary — most reliable signal.
    for source in (summary, md):
        m = _YEARS_RE.search(source or "")
        if m:
            n = int(m.group(1))
            if 0 < n <= 60:
                return n
    # Fall back to the span of years mentioned in the experience section.
    years = [int(y) for y in re.findall(r"(?:19|20)\d{2}", experience or "")]
    if years:
        start = min(years)
        end = datetime.date.today().year if _PRESENT_RE.search(experience or "") else max(years)
        span = end - start
        if 0 < span <= 60:
            return span
    return 0



def _normalize_heading_title(raw: str) -> list[str]:
    s = raw.strip()
    if not s.startswith("###"):
        return []
    s = s.lstrip("#").strip()
    # Drop trailing date ranges and split company/title separators.
    s = _YEAR_TOKEN_RE.split(s)[0]
    s = _MONTH_RE.sub(" ", s)
    s = re.sub(r"[|–—\-]+\s*$", "", s).strip(" |,-–—")
    segs = [x.strip(" ,") for x in
            re.split(r"\s*[|–—,]\s*|\s+at\s+|\s+@\s+", s) if x.strip(" ,")]
    return [x for x in segs if 2 <= len(x.split()) <= 7 and not re.search(r"\d", x)]


def _extract_titles(experience: str, summary: str, head: str = "") -> list[str]:
    """Best-effort role titles, ordered from most-recent to older."""
    # PDF ingest renders dated role lines as "### <role line with a year>".
    headings: list[list[str]] = []
    for line in (experience or "").splitlines():
        segs = _normalize_heading_title(line.strip())
        if segs:
            headings.append(segs)

    # Both "Title | Company" and "Company | Title" are common, so position can't
    # decide it — the segment naming a role is the title.
    titles: list[str] = []
    for segs in headings:
        for seg in segs:
            if _ROLE_WORD_RE.search(seg):
                if seg not in titles:
                    titles.append(seg)
    # No role word anywhere: the summary opening ("Senior SRE with 9 years…") is a
    # better guess than a heading that is probably the employer's name.
    if titles:
        return titles
    first = (summary or "").strip().splitlines()[0] if summary else ""
    first = re.split(r"\s+with\s+|\s*[.,]\s*", first, maxsplit=1)[0].strip()
    if first and 1 <= len(first.split()) <= 7 and not re.search(r"\d", first):
        return [first]
    for segs in headings:
        for seg in segs:
            if not _CORP_SUFFIX_RE.search(seg):
                return [seg]

    # Last resort: the headline. Most résumés put the role on the line under the
    # name, and a two-column layout can defeat every rule above — a PDF whose
    # sidebar merged into the body produced "## SKILLS WORK EXPERIENCE", so no
    # experience section was recognised and both inputs here arrived empty.
    return _headline_title(head)


def _headline_title(head: str) -> list[str]:
    for raw in (head or "").splitlines()[:8]:
        line = raw.strip().lstrip("#").strip()
        if not line or "@" in line or _URL_RE.search(line):
            continue
        if re.search(r"\d", line) or len(line.split()) > 7:
            continue
        if _ROLE_WORD_RE.search(line):
            return [line]
    return []


_ADJACENT_ROLES = {
    "site reliability": ["Platform Engineer", "Infrastructure Engineer",
                         "DevOps Engineer", "Cloud Engineer"],
    "devops":           ["Site Reliability Engineer", "SRE", "Platform Engineer",
                         "Infrastructure Engineer"],
    "platform engineer": ["Site Reliability Engineer", "SRE",
                          "Infrastructure Engineer", "DevOps Engineer"],
    "mlops":            ["MLOps Engineer", "AIOps Engineer",
                         "Machine Learning Engineer", "Platform Engineer"],
    "aiops":            ["AIOps Engineer", "MLOps Engineer", "SRE",
                         "Observability Engineer"],
    "infrastructure":   ["Infrastructure Engineer", "Platform Engineer",
                         "Site Reliability Engineer", "Cloud Engineer"],
    "cloud engineer":   ["Cloud Engineer", "Platform Engineer",
                         "Infrastructure Engineer", "DevOps Engineer"],
    "data engineer":    ["Data Engineer", "Analytics Engineer",
                         "Data Platform Engineer"],
    "backend":          ["Backend Engineer", "Software Engineer",
                         "Platform Engineer"],
}


def _title_aliases(title: str) -> list[str]:
    out: list[str] = []

    def _add(candidate: str) -> None:
        candidate = re.sub(r"\s+", " ", candidate).strip(" ,")
        if candidate and candidate not in out:
            out.append(candidate)

    _add(title)
    stripped = _SENIORITY_PREFIX_RE.sub("", title).strip()
    if stripped and stripped != title:
        _add(stripped)

    lower = title.lower()
    if "site reliability engineer" in lower or lower.strip() == "sre":
        _add("SRE")
        _add("Site Reliability Engineer")
    if "devops" in lower:
        _add("DevOps Engineer")
    if "platform engineer" in lower:
        _add("Platform Engineer")

    # Adjacent roles. A résumé names the jobs someone has held, which is a
    # narrower set than the jobs they can get: an SRE is read for Platform,
    # Infrastructure, Cloud and DevOps openings too. Without this a new profile
    # searches only the words already on the CV, and discovery reads eleven
    # thousand postings to keep about fifty.
    for trigger, neighbours in _ADJACENT_ROLES.items():
        if trigger in lower:
            for n in neighbours:
                _add(n)
            break
    return out


def extract_profile_fields(md: str) -> dict[str, Any]:
    """Return only the fields we could confidently pull from the résumé."""
    out: dict[str, Any] = {}
    if not md or not md.strip():
        return out

    sections = parse_cv_markdown(md)
    contact_blob = "\n".join(filter(None, [sections.name, sections.contact, md[:600]]))

    name = infer_cv_name(md, sections)
    email = _first_email(contact_blob) or _first_email(md)
    phone = _first_phone(contact_blob) or _first_phone(md)
    linkedin = _first(_LINKEDIN_RE, md)
    github = _first(_GITHUB_RE, md)
    location = (_extract_location(sections.contact or md[:400])
                or _location_from_contact_row(md))
    years_exp = _extract_years_exp(md, sections.summary, sections.experience)
    titles = _extract_titles(sections.experience, sections.summary, md[:600])

    if name:
        out["name"] = name
    if email:
        out["email"] = email
    if phone:
        out["phone"] = phone
    if linkedin:
        out["linkedin"] = linkedin
    if github:
        out["github"] = github
    if location:
        out["location"] = location
        # Seed preferred locations with the home city so targeting isn't global.
        city = location.split(",")[0].strip()
        if city:
            out["preferred_locations"] = [city]
    if years_exp:
        out["years_exp"] = years_exp
    if titles:
        expanded: list[str] = []
        # Every title gets expanded, not only the first. Expanding titles[0]
        # alone is why a fresh onboarding produced five target titles where the
        # same CV should give a dozen: discovery still reads ~11,000 postings a
        # scan, but the title filter throws away almost everything that isn't
        # the one role the résumé happened to list first.
        for title in titles[:6]:
            for alias in _title_aliases(title):
                if alias not in expanded:
                    expanded.append(alias)
        del expanded[16:]
        out["target_titles"] = expanded

    return out
