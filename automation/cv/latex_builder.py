"""Build filled LaTeX from cv.md + template."""

from __future__ import annotations

import os
import re
import subprocess
from datetime import datetime

from config import SHORTLISTR_ROOT, CV_MD_PATH, OUTPUT_DIR
from cv.ats_score import score_ats_readiness
from cv.latex_layout import (
    DEFAULT_DENSITY,
    DENSITY_LADDER,
    build_preamble,
    density_by_name,
)
from cv.normalize import normalize_cv
from cv.parser import parse_cv_markdown, sections_to_plain_blocks
from cv.reflow import parse_blocks
from cv.templates import get_template, template_path
from store.settings import get_cv_settings, set_cv_settings

_LATEX_ESC = str.maketrans(
    {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
        # Punctuation a word processor substitutes silently, which T1-encoded
        # fonts then render as something else entirely: the "·" separating a
        # candidate's phone from their email came out as "ů" in their contact
        # line. Mapped to commands rather than left as bytes, so the output does
        # not depend on which LaTeX engine happens to be installed.
        "·": r"\textperiodcentered{}",
        "•": r"\textbullet{}",
        "–": "--",
        "—": "---",
        "‘": "`",
        "’": "'",
        "“": "``",
        "”": "''",
        "…": r"\ldots{}",
        "°": r"\textdegree{}",
        "™": r"\texttrademark{}",
        "®": r"\textregistered{}",
        "€": r"\texteuro{}",
        # "Rs." rather than \rupee{}, which needs a package this document does
        # not load — an Indian resume saying "managed a ₹4.5 crore budget" made
        # the whole compile fail and fall back silently to the HTML renderer.
        "₹": "Rs.",
        " ": " ",
        "​": "",
        "﻿": "",
    }
)


def _escape_latex(text: str) -> str:
    if not text:
        return ""
    return text.translate(_LATEX_ESC)


def _inline(text: str) -> str:
    """Escape LaTeX specials, then honour **bold** and *italic*.

    Order matters and is the reverse of what looks natural: escaping first is
    what makes this safe, because after it the only backslashes in the string
    are ones we put there. Converting markdown first would leave a candidate's
    literal "C++ & 100%" to be escaped afterwards along with our own commands.
    """
    t = _escape_latex(text)
    t = re.sub(r"\*\*(.+?)\*\*", r"\\textbf{\1}", t)
    t = re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", r"\\textit{\1}", t)
    return t


# "Cloud & Platforms: AWS, Kubernetes, …" — a skills line names its category and
# then lists it. Emphasising the category is what lets a reader (and a recruiter
# skimming for six seconds) find the row they care about. Kept deliberately tight:
# a label is short, sits before the first colon, and holds no sentence-ending
# punctuation, so a real sentence that happens to contain a colon stays prose.
_LEAD_LABEL = re.compile(r"^([^:.!?\n]{2,42}):\s+(?=\S)")


def _emphasise_label(text: str) -> str:
    """Bold a leading "Category:" if the line has one. Otherwise unchanged."""
    m = _LEAD_LABEL.match(text)
    if not m or "**" in text:
        return _inline(text)
    return rf"\textbf{{{_inline(m.group(1))}:}} {_inline(text[m.end():])}"


def _split_when(heading: str) -> tuple[str, str]:
    """("what they did", "when") — dates lifted out of a role heading.

    A resume writes "Wipro - Senior Engineer (2019-2026)" as often as it puts
    the dates on their own line. Lifting them lets the template flush them
    right, so a reader scans the timeline down one edge instead of hunting for
    it inside each title.
    """
    from cv.normalize import _DATE_RANGE

    m = _DATE_RANGE.search(heading)
    if not m:
        return heading, ""
    what = (heading[:m.start()] + " " + heading[m.end():])
    what = re.sub(r"\s*[(\[]\s*[)\]]\s*", " ", what)      # the empty brackets left behind
    what = re.sub(r"\s{2,}", " ", what).strip(" ,;:-–—([{")
    return (what or heading), m.group(0).strip()


def _md_to_latex_body(text: str) -> str:
    """Canonical resume markdown → LaTeX.

    Structure-aware: a `### Role` line followed by its dates becomes one
    `\\entry` — the role on the left, the dates flush right on the same line —
    instead of two bold paragraphs stacked on top of each other with no
    relationship between them. That relationship is most of what makes a
    résumé look typeset rather than dumped.

    Line joining lives in `cv/reflow.py`, shared with the HTML preview so the
    two renderers cannot drift apart on structure.
    """
    out: list[str] = []
    for block in parse_blocks(text, split_when=_split_when):
        if block.kind == "entry":
            out.append(rf"\entry{{{_inline(block.text)}}}{{{_inline(block.when)}}}")
        elif block.kind == "meta":
            out.append(rf"\entrymeta{{{_inline(block.text)}}}")
        elif block.kind == "bullets":
            out.append(r"\begin{itemize}")
            out.extend(r"\item " + _inline(item) for item in block.items)
            out.append(r"\end{itemize}")
        elif block.text:
            out.append(_emphasise_label(block.text) + r"\par")
    return "\n".join(out)


# Anything that identifies a channel rather than a role.
_CONTACT_HINT = re.compile(
    r"@|https?://|\+?\d[\d\s\-()]{7,}|linkedin\.com|github\.com", re.I
)


def _contact_latex(raw: str) -> str:
    """The block above the first section: an optional headline, then details.

    Joining every preamble line with " · " produced
    "…Agentic AI** ·  · Bangalore, India • +91…" — an unclosed bold marker
    (the leading ** had been stripped and its partner had not), and an empty
    segment where the blank line between the two paragraphs used to be.
    """
    lines = [re.sub(r"^\*+|\*+$", "", l.strip()).strip() for l in raw.splitlines()]
    lines = [l for l in lines if l]
    if not lines:
        return ""
    headline = ""
    if len(lines) > 1 and not _CONTACT_HINT.search(lines[0]):
        headline = lines.pop(0)
    out = _inline(" · ".join(lines))
    if headline:
        out = rf"\cvheadline{{{_inline(headline)}}}" + "\n" + out
    return out


_SECTION_TITLES = (
    ("summary", "Summary"), ("skills", "Skills"), ("experience", "Experience"),
    ("projects", "Projects"), ("education", "Education"),
    ("certifications", "Certifications"), ("additional", "Additional"),
)


def build_latex(md: str, template_id: str, *, density: int = DEFAULT_DENSITY) -> str:
    """Fill a template. `density` indexes DENSITY_LADDER — see fit_to_pages."""
    tpl = get_template(template_id)
    if not tpl:
        raise ValueError(f"Unknown template: {template_id}")
    raw_tpl = open(template_path(template_id), encoding="utf-8").read()

    # Give the document a shape before trying to typeset it. A CV extracted
    # from a PDF has no headings at all, so without this the parser finds no
    # sections and the whole resume renders as one blob under the contact line.
    md = normalize_cv(md)

    sections = parse_cv_markdown(md)
    blocks = sections_to_plain_blocks(sections)

    name = sections.name or "Candidate"

    rung = DENSITY_LADDER[max(0, min(density, len(DENSITY_LADDER) - 1))]
    replacements = {
        "{{PREAMBLE}}": build_preamble(
            rung, pdf_title=f"{name} — Resume", pdf_author=name
        ),
        "{{NAME}}": _escape_latex(name),
        "{{CONTACT}}": _contact_latex(blocks["contact"] or blocks.get("name", "")),
    }
    for key, default_title in _SECTION_TITLES:
        body = _md_to_latex_body(blocks.get(key, ""))
        if not body.strip():
            # An empty section is omitted, not filled with a placeholder.
            # "Certifications / [Add section in cv.md]" was printed at everybody
            # who had none, and it reads as an unfinished document — on the one
            # page that is supposed to argue for them.
            replacements["{{%s}}" % key.upper()] = ""
        else:
            title = tpl.section_titles.get(key, default_title)
            replacements["{{%s}}" % key.upper()] = f"\\cvsection{{{title}}}\n{body}\n"

    tex = raw_tpl
    for k, v in replacements.items():
        tex = tex.replace(k, v)
    return tex


LATEX_TIMEOUT = 120

# Tried in order. Tectonic first because it is one binary that fetches whatever
# packages a document needs and caches them — no TeX distribution to install,
# and one line in a container. The others are honoured when a machine already
# has a full TeX Live and would rather use it.
LATEX_ENGINES = (
    ("tectonic", lambda tex, out: [
        "tectonic", "-X", "compile", "--outdir", out, "--keep-logs", tex]),
    ("xelatex", lambda tex, out: [
        "xelatex", "-interaction=nonstopmode", "-output-directory", out, tex]),
    ("pdflatex", lambda tex, out: [
        "pdflatex", "-interaction=nonstopmode", "-output-directory", out, tex]),
)


def latex_available() -> str:
    """The first usable engine's name, or "" if none is installed."""
    import shutil

    for name, _argv in LATEX_ENGINES:
        if shutil.which(name):
            return name
    return ""


_LATEX_BYPRODUCTS = (".log", ".aux", ".out", ".synctex.gz")


def _clear_byproducts(pdf_path: str) -> None:
    """Drop the build scratch files a successful compile leaves behind.

    `output/` is where the user goes to pick up a résumé to attach to an
    application, so it has to contain résumés. Tectonic runs with --keep-logs
    (that log is the only place a LaTeX error is legible), and the page-fit
    search compiles up to four times, so a single generate could leave the
    folder holding more scratch files than documents. They are only deleted on
    success — a failed compile needs its log.
    """
    stem = os.path.splitext(pdf_path)[0]
    for ext in _LATEX_BYPRODUCTS:
        try:
            os.remove(stem + ext)
        except OSError:
            pass


def compile_tex(tex_path: str, pdf_path: str) -> tuple[bool, str | None, str | None]:
    """Compile to PDF. Returns (ok, error, engine-that-worked).

    Never raises: the caller has an HTML fallback, and a resume that renders
    slightly worse beats a candidate with no resume. The engine's own error is
    kept and returned, because "LaTeX failed" with no detail is unactionable
    when it happens to one person's CV and nobody else's.
    """
    out_dir = os.path.dirname(pdf_path) or "."
    last = None
    for name, argv in LATEX_ENGINES:
        try:
            proc = subprocess.run(argv(tex_path, out_dir), capture_output=True,
                                  timeout=LATEX_TIMEOUT, check=False, cwd=out_dir)
        except FileNotFoundError:
            continue                        # engine not installed; try the next
        except Exception as e:              # noqa: BLE001
            last = f"{name}: {e}"
            continue
        if os.path.isfile(pdf_path):
            _clear_byproducts(pdf_path)
            return True, None, name
        tail = (proc.stderr or proc.stdout or b"").decode("utf-8", "replace")
        last = f"{name}: {tail.strip()[-400:] or 'produced no PDF'}"
    return False, last, None


def pdf_page_count(pdf_path: str) -> int:
    """Pages in a PDF, or 0 if it cannot be read."""
    try:
        from pypdf import PdfReader

        return len(PdfReader(pdf_path).pages)
    except Exception:
        return 0


# Each attempt is a full LaTeX run — a few seconds even on a warm tectonic
# cache — so the search starts from an estimate rather than from the middle of
# the ladder, and stops early.
MAX_FIT_COMPILES = 4

# Roughly how many characters of source each rung fits on a page. Calibrated
# against real résumés, not derived: bullets, section headings and the header
# all cost more vertical space than their character count suggests, and the
# ratio between them is what the ladder actually changes. Only used to choose
# a starting rung — the page count that decides anything is measured.
_CHARS_PER_PAGE = (2900, 3100, 3400, 3900, 4300, 4700)


def _start_density(body_chars: int, target: int, ceiling: int) -> int:
    for i, cap in enumerate(_CHARS_PER_PAGE[: ceiling + 1]):
        if body_chars <= cap * target:
            return i
    return ceiling


def fit_to_pages(
    md: str,
    template_id: str,
    tex_path: str,
    pdf_path: str,
    *,
    page_target: str | int = "auto",
) -> dict:
    """Compile repeatedly until the résumé holds the requested page count.

    "Fits on one page" is the only claim about a résumé a user can check at a
    glance, and the only one this repo used to get wrong: the HTML preview
    shrank text with a script until it fit, then clipped whatever was still
    over, so content silently disappeared off the bottom. Here the page count
    is measured from the compiled PDF and the remedy is a denser layout —
    nothing is ever cut.

    The search wants the *roomiest* layout that fits, not the first one. A
    two-page résumé squeezed to 10pt when 11pt would also have made two pages
    is just harder to read for nothing.
    """
    tpl = get_template(template_id)
    ceiling = density_by_name(tpl.max_density) if tpl else len(DENSITY_LADDER) - 1
    body_chars = len(re.sub(r"\s+", " ", md or ""))

    attempts: list[dict] = []

    def attempt(density: int) -> dict:
        for a in attempts:
            if a["density"] == density:
                return a
        with open(tex_path, "w", encoding="utf-8") as f:
            f.write(build_latex(md, template_id, density=density))
        ok, err, engine = compile_tex(tex_path, pdf_path)
        result = {
            "density": density, "ok": ok, "error": err, "engine": engine,
            "pages": pdf_page_count(pdf_path) if ok else 0,
        }
        attempts.append(result)
        return result

    def search(target: int) -> dict:
        best = attempt(_start_density(body_chars, target, ceiling))
        if not best["ok"]:
            return best
        cur = best["density"]
        if best["pages"] > target:
            # Too long: tighten a rung at a time until it fits or we run out.
            while (best["pages"] > target and cur < ceiling
                   and len(attempts) < MAX_FIT_COMPILES):
                cur += 1
                trial = attempt(cur)
                if trial["ok"]:
                    best = trial
        else:
            # Already fits: hand the page back its whitespace while it still does.
            while cur > 0 and len(attempts) < MAX_FIT_COMPILES:
                trial = attempt(cur - 1)
                if not trial["ok"] or trial["pages"] > target:
                    break
                best, cur = trial, cur - 1
        return best

    if page_target in ("1", 1, "one"):
        target, auto = 1, False
    elif page_target in ("2", 2, "two"):
        target, auto = 2, False
    else:
        # Auto prefers one page but will not spend a compile proving the
        # impossible: a CV this far over the densest rung's capacity is a
        # two-page résumé, and two pages for a long career is normal.
        target, auto = (1 if body_chars <= _CHARS_PER_PAGE[ceiling] else 2), True

    best = search(target)
    if best["ok"] and best["pages"] > target and auto and target == 1:
        target = 2
        best = search(target)

    if not best["ok"]:
        return best | {"fitted": False, "target_pages": target}

    # The loop may have left a later trial's .tex on disk. The download and the
    # PDF have to be the same document, so put the winner back.
    if best["density"] != attempts[-1]["density"]:
        with open(tex_path, "w", encoding="utf-8") as f:
            f.write(build_latex(md, template_id, density=best["density"]))
        ok, err, engine = compile_tex(tex_path, pdf_path)
        best = best | {"ok": ok, "error": err, "engine": engine}

    return best | {"fitted": best["pages"] <= target, "target_pages": target,
                   "density_name": DENSITY_LADDER[best["density"]].name,
                   "compiles": len(attempts)}


def save_cv_markdown(md: str) -> str:
    path = CV_MD_PATH
    os.makedirs(os.path.dirname(path) or SHORTLISTR_ROOT, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(md.strip() + "\n")
    return path


def generate_cv_artifacts(
    *,
    template_id: str,
    md: str | None = None,
    tenant_id: str = "default",
    page_target: str | int = "auto",
) -> dict:
    if md is None:
        if not os.path.isfile(CV_MD_PATH):
            raise FileNotFoundError("cv.md not found — complete onboarding first")
        md = open(CV_MD_PATH, encoding="utf-8").read()
    else:
        save_cv_markdown(md)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    date = datetime.now().strftime("%Y-%m-%d")
    sections = parse_cv_markdown(md)
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", (sections.name or "cv")).strip("-")[:40]
    tex_path = os.path.join(OUTPUT_DIR, f"{slug}-ats-{template_id}-{date}.tex")
    pdf_path = os.path.join(OUTPUT_DIR, f"{slug}-ats-{template_id}-{date}.pdf")

    fit = fit_to_pages(md, template_id, tex_path, pdf_path, page_target=page_target)
    pdf_ok = bool(fit.get("ok"))
    pdf_error = fit.get("error")
    pdf_engine = fit.get("engine")
    pages = fit.get("pages", 0)

    if not pdf_ok:
        # No LaTeX engine, or this document does not compile. Render the HTML
        # preview through Chromium instead — a résumé that is typeset slightly
        # worse beats a candidate with no résumé. The .tex is still on disk, so
        # the user can compile it on Overleaf and get the intended output.
        try:
            from cv.preview import render_cv_html
            from generate_pdf import generate_pdf_from_html

            html_doc = render_cv_html(md, template_id, single_page=True)
            generate_pdf_from_html(html_doc, pdf_path, fmt="A4", full_sheet=True)
            pdf_ok = os.path.isfile(pdf_path)
            if pdf_ok:
                pdf_engine = "playwright"
                pages = pdf_page_count(pdf_path)
        except Exception as e:
            pdf_error = (f"PDF render failed — LaTeX: {pdf_error or 'no engine installed'}; "
                         f"Playwright fallback: {e}")

    if not pdf_ok and not pdf_error:
        pdf_error = "Could not produce PDF — install tectonic (brew install tectonic) or Playwright (Connections → Install Playwright)"

    ats = score_ats_readiness(md, template_id=template_id)
    set_cv_settings(
        {
            "template_id": template_id,
            "last_generated_tex": tex_path,
            "last_generated_pdf": pdf_path if pdf_ok else None,
            "ats_score": ats["score"],
            "page_target": page_target,
            "last_page_count": pages,
            "last_density": fit.get("density_name"),
        },
        tenant_id=tenant_id,
    )

    return {
        "template_id": template_id,
        "tex_path": tex_path,
        "pdf_path": pdf_path if pdf_ok else None,
        "pdf_ok": pdf_ok,
        "pdf_engine": pdf_engine,
        "pdf_error": pdf_error,
        "pages": pages,
        "page_target": fit.get("target_pages"),
        "fitted": fit.get("fitted", False),
        "density": fit.get("density_name"),
        "ats": ats,
        "cv_path": CV_MD_PATH,
    }
