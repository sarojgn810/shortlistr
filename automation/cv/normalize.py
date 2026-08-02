"""Giving a resume a shape before anything tries to typeset it.

A CV arrives as a PDF. Extracting text from a PDF gives back lines, not
structure: no headings, no entries, no idea which run of text is a job and
which is a skills list. `parse_cv_markdown` then looks for `##` headings, finds
none, and drops the entire document into `contact`.

That is not a hypothetical. A real candidate's tailored resume — one that went
to a referrer — rendered as their name followed by 7,780 characters of
undifferentiated text, zero section headings, and the literal angle brackets
their PDF had wrapped job titles in. Every template in the repo produces that,
because every template is fed the same shapeless blob. Choosing a nicer one
changes the font on a wall of text.

Worse, it compounds: the tailoring prompt says "keep the exact markdown section
structure and headers of the input resume", which is right for a structured
input and means "preserve the mess" for an unstructured one.

So this module imposes a shape. One canonical form, which every template can
rely on:

    # Name
    **phone · email · location · links**
    ## Summary
    ## Skills
    ## Experience
    ### Title — Company
    *Dates · Location*
    - bullet
    ## Education
    ## Certifications

Deterministic by construction. There is an optional LLM pass for documents the
heuristics cannot segment, but it can only ever *re-label* text — the fallback
is the heuristic result, never an empty document, and nothing here invents a
line the source did not contain. A resume is a factual claim about somebody's
life and this file is the wrong place to be creative.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# Glyphs a PDF extractor leaves where a bullet used to be. The first is the
# private-use codepoint Word ships for Symbol-font bullets, which is why these
# resumes are full of characters that render as nothing at all.
_BULLET_GLYPHS = "•▪●‣⁃·"
_BULLET_LINE = re.compile(rf"^\s*[{_BULLET_GLYPHS}\-\*–—]\s+")

_CANONICAL = ("Summary", "Skills", "Experience", "Projects", "Education",
              "Certifications", "Additional")

# Which canonical section a heading in the wild belongs to. Longest first, so
# "professional experience" is not eaten by "experience".
_HEADING_MAP = (
    ("Summary", ("professional summary", "career summary", "executive summary",
                 "profile summary", "summary", "profile", "objective",
                 "career objective", "about me", "about")),
    ("Skills", ("technical skillset", "overall skillset", "core competencies",
                "technical skills", "core skills", "key skills", "skillset",
                "technical proficiencies", "competencies", "skills",
                "technologies", "tech stack")),
    ("Experience", ("professional experience", "work experience",
                    "employment history", "career history", "experience",
                    "employment", "work history")),
    ("Education", ("education and training", "academic qualifications",
                   "educational qualifications", "qualifications", "education",
                   "academics")),
    ("Certifications", ("certifications and licenses", "certifications",
                        "certificates", "licenses", "courses",
                        "professional development")),
    ("Projects", ("key projects", "selected projects", "projects",
                  "personal projects", "project experience")),
    # Real sections that are none of the above. Without a home they were
    # swallowed into whatever section preceded them: "Extracurricular
    # Activities" rendered as three more bullets on somebody's last job.
    ("Additional", ("extracurricular activities", "extra curricular",
                    "activities and interests", "awards and honours",
                    "awards and honors", "achievements", "awards",
                    "honours", "honors", "interests", "hobbies", "languages",
                    "publications", "volunteering", "additional information")),
)

# A date range, in the many shapes a resume writes one. Used to find where a job
# entry begins, which is the single most useful signal in an unstructured CV.
_MONTH = (r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*")
_YEAR = r"(?:19|20)\d{2}"
# The apostrophe in "Jan '24" is whatever the word processor felt like: ASCII,
# or one of two curly variants. Missing the curly ones meant every job at a
# company that writes dates that way was filed as a bullet instead of an entry
# — which is most of them, since Word substitutes the curly form by default.
_APOS = r"['‘’ʼ`]"
_DATE_POINT = (rf"(?:{_MONTH}\.?\s*{_APOS}?\s*\d{{2,4}}"
               rf"|{_MONTH}\.?\s*{_YEAR}|{_YEAR}|\d{{1,2}}/\d{{2,4}})")
_DATE_RANGE = re.compile(
    rf"({_DATE_POINT})\s*(?:-|–|—|to|until|through)\s*"
    rf"({_DATE_POINT}|present|current|date|now|till\s*date)",
    re.I)

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_PHONE = re.compile(r"(?:\+\d{1,3}[\s-]?)?(?:\d[\s-]?){9,13}")
_URL = re.compile(r"(?:https?://|www\.)\S+|linkedin[\w./-]*", re.I)


def _clean_line(line: str) -> str:
    """One line, with the artefacts of PDF extraction taken off it."""
    t = line.replace("﻿", "").replace(" ", " ")
    # "<Consultant Technology Solutions>" — some exporters wrap every field in
    # angle brackets, and they survive all the way to the rendered PDF.
    t = re.sub(r"<([^<>]{2,80})>", r"\1", t)
    t = t.translate({ord(c): "•" for c in ""})
    t = re.sub(r"[ \t]{2,}", " ", t)
    return t.rstrip()


def _heading_for(line: str) -> str:
    """The canonical section this line announces, or "".

    Tolerant of how people actually write headings: "PROFESSIONAL EXPERIENCE
    (7 Years & 9 months)", "Skills:", "## Education". Intolerant of long lines,
    because a sentence that merely mentions "experience" is not a heading.
    """
    t = re.sub(r"^#{1,6}\s*", "", (line or "").strip())
    t = re.sub(r"\([^)]*\)", " ", t)                  # "(7 Years & 9 months)"
    t = re.sub(r"[^a-zA-Z ]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip().lower()
    if not t or len(t) > 45:
        return ""
    # Plural-insensitive: a CV says "Educational Qualification" as often as
    # "Educational Qualifications", and matching only one spelling filed the
    # whole education section as bullets on the previous job.
    singular = re.sub(r"s\b", "", t)
    for canon, names in _HEADING_MAP:
        for n in names:
            for cand in (t, singular):
                ns = re.sub(r"s\b", "", n)
                if cand in (n, ns) or cand.startswith(ns + " ") \
                        or cand.endswith(" " + ns):
                    return canon
    return ""


def looks_structured(md: str) -> bool:
    """Whether this markdown already carries sections worth keeping.

    Two is the threshold on purpose: one heading is as likely to be a stray line
    starting with "#" as a real section, and re-imposing structure on a document
    that has it is how a good resume gets flattened.
    """
    found = {_heading_for(l) for l in (md or "").splitlines() if l.startswith("#")}
    return len({f for f in found if f}) >= 2


def _split_head(lines: list[str]) -> tuple[str, str, int]:
    """(name, contact, index where the body starts).

    The top of a resume is a name and a way to reach them, and neither is
    labelled. Taken positionally, which is the only thing that is reliable.
    """
    name, contact_bits, i = "", [], 0
    while i < len(lines) and i < 8:
        raw = lines[i].strip()
        if not raw:
            i += 1
            continue
        if _heading_for(raw):
            break
        plain = re.sub(r"^#{1,6}\s*|\*", "", raw).strip()
        has_contact = bool(_EMAIL.search(plain) or _URL.search(plain)
                           or (_PHONE.search(plain) and len(plain) < 120))
        if not name and not has_contact and 3 <= len(plain) <= 60:
            name = plain
            i += 1
            continue
        if has_contact:
            contact_bits.append(plain)
            i += 1
            continue
        break
    contact = " · ".join(
        re.sub(r"\s*[|·,]\s*", " · ", c).strip(" ·") for c in contact_bits)
    return name, contact, i


def _entry_heading(line: str) -> tuple[str, str] | None:
    """(what they did, when) if this line opens a job or a degree, else None.

    A date range on a short line is the marker. It is not perfect and does not
    need to be: a missed entry becomes a bullet, which is untidy, while a false
    positive would invent a job, which is not acceptable.
    """
    t = line.strip()
    if not t or len(t) > 160 or _BULLET_LINE.match(t):
        return None
    m = _DATE_RANGE.search(t)
    if not m:
        return None
    what = (t[:m.start()] + " " + t[m.end():]).strip(" .,;:|-–—\t")
    what = re.sub(r"\s*[|,]\s*", " — ", what)
    what = re.sub(r"\s{2,}", " ", what).strip(" —")
    if not what:
        return None
    return what, m.group(0).strip()


def _rejoin_wrapped(lines: list[str]) -> list[str]:
    """Put back the lines a PDF broke in the middle of a sentence.

    A PDF has no paragraphs, only lines at whatever width the page was. Bulleting
    each one turns "...driving market growth and / expansion." into two bullets,
    the second of which is the word "expansion." — which is how these resumes
    read today.

    Joined only when the break is obviously mid-sentence: the line does not end
    in terminal punctuation and the next begins lowercase, with a digit, or
    with a conjunction. Digits count because "increasing throughput by\n2x."
    left "2x." sitting alone as its own bullet. Lines carrying a date range or
    a heading are excluded first, so nothing structural is swallowed.
    """
    out: list[str] = []
    for raw in lines:
        cur = raw.rstrip()
        prev = out[-1] if out else ""
        stripped = cur.strip()
        # Never absorb a line that is somebody's contact details. Allowing a
        # digit to continue a sentence is what makes "throughput by\n2x." work,
        # and it also merged the name line into the phone number underneath it,
        # leaving the resume with no name at all.
        is_contact = bool(_EMAIL.search(stripped) or _URL.search(stripped)
                          or _PHONE.match(stripped))
        if (prev and stripped and not is_contact and not _BULLET_LINE.match(cur)
                and not _heading_for(cur) and not _DATE_RANGE.search(cur)
                and not prev.rstrip().endswith((".", ":", ";", "!", "?"))
                and prev.strip()
                and (stripped[0].islower() or stripped[0].isdigit()
                     or stripped[0] in "&,)$%")):
            # A page break inside a word leaves a trailing hyphen. Keep it:
            # "client-\naligned" is far more often the real compound
            # "client-aligned" than a broken "clientaligned", and dropping it
            # produced exactly that word in a real candidate's resume.
            if prev.rstrip().endswith("-"):
                out[-1] = prev.rstrip() + stripped
            else:
                out[-1] = prev.rstrip() + " " + stripped
            continue
        out.append(cur)
    return out


def _segment(lines: list[str], start: int) -> dict[str, list[str]]:
    """Body lines grouped under the canonical section they fall in.

    Text before any recognisable heading goes to Summary — at the top of a
    resume that is what it almost always is, and losing it entirely would be
    worse than filing it imperfectly.
    """
    out: dict[str, list[str]] = {s: [] for s in _CANONICAL}
    current = "Summary"
    for raw in lines[start:]:
        line = _clean_line(raw)
        if not line.strip():
            out[current].append("")
            continue
        head = _heading_for(line)
        if head:
            current = head
            continue
        out[current].append(line)
    return out


def _render_section(name: str, body: list[str]) -> str:
    """One section as canonical markdown, or "" if it has nothing in it.

    An empty section is omitted rather than printed with a placeholder. The
    templates used to render "Certifications / [Add section in cv.md]" at
    anybody who had none, which reads as an unfinished document.
    """
    text = "\n".join(body).strip()
    if not text:
        return ""
    lines_out = [f"## {name}", ""]
    if name in ("Experience", "Projects", "Education"):
        for raw in text.splitlines():
            if not raw.strip():
                continue
            entry = _entry_heading(raw)
            if entry:
                what, when = entry
                lines_out += ["", f"### {what}", f"*{when}*", ""]
            elif _BULLET_LINE.match(raw):
                lines_out.append("- " + _BULLET_LINE.sub("", raw).strip())
            else:
                lines_out.append("- " + raw.strip())
    else:
        for raw in text.splitlines():
            if not raw.strip():
                continue
            if _BULLET_LINE.match(raw):
                lines_out.append("- " + _BULLET_LINE.sub("", raw).strip())
            else:
                lines_out.append(raw.strip())
    return "\n".join(lines_out).strip() + "\n"


def normalize_cv(md: str, *, force: bool = False) -> str:
    """A resume in the one shape every template is written against.

    Returns the input unchanged when it already has sections, unless `force`.
    Never returns less than it was given: if segmentation finds nothing, the
    original is handed back rather than an empty skeleton.
    """
    src = (md or "").strip()
    if not src:
        return ""
    if not force and looks_structured(src):
        return "\n".join(_clean_line(l) for l in src.splitlines()).strip() + "\n"

    # Angle-bracket wrappers are stripped across the whole document, not per
    # line: some exporters wrap each field in "<...>" and the page then breaks
    # inside one, so "<Associate Consultant Technology\nSolutions>" left a
    # stray "<" opening a bullet and a stray ">" opening the next job's title.
    # The newline inside the wrapper is collapsed too, not just the brackets:
    # "<Associate Consultant Technology\nSolutions>" is one job title that the
    # page happened to break, and leaving the break made the half with the date
    # on it the entry and orphaned the other half as a bullet.
    src = re.sub(r"<([^<>]{2,120}?)>",
                 lambda m: re.sub(r"\s*\n\s*", " ", m.group(1)), src, flags=re.S)
    lines = _rejoin_wrapped([_clean_line(l) for l in src.splitlines()])
    name, contact, start = _split_head(lines)
    sections = _segment(lines, start)

    rendered = [_render_section(s, sections[s]) for s in _CANONICAL]
    if not any(rendered):
        logger.warning("normalize_cv: nothing segmented; keeping the original")
        return src + "\n"

    out = []
    if name:
        out.append(f"# {name}\n")
    if contact:
        out.append(f"**{contact}**\n")
    out += [r for r in rendered if r]
    return "\n".join(out).strip() + "\n"
