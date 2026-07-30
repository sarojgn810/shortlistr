"""The LaTeX path, end to end, including whether it actually compiles.

Building a .tex that looks right and compiling one are different things, and
only the second reaches a candidate. These tests run the real engine when one
is installed and skip when it is not, because a machine without LaTeX is a
supported configuration — the caller falls back to the HTML renderer.

The escaping cases are the ones that matter most. A single undefined command
from one candidate's punctuation fails the whole document, and the failure is
silent: they get the plainer HTML resume and nobody finds out. "₹4.5 crore" did
exactly that.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "automation"))

import pytest

from cv.latex_builder import (build_latex, compile_tex, latex_available,
                              _md_to_latex_body)

ENGINE = latex_available()
needs_latex = pytest.mark.skipif(not ENGINE, reason="no LaTeX engine installed")

CV = """Asha M
asha@example.com | +91 90000 00000

Professional Summary
Site reliability engineer with 6 years across cloud infrastructure.

Skills
Kubernetes, Terraform, AWS, Python

Work Experience

AcmeCloud - Site Reliability Engineer (2021 - present)
- Cut incident MTTR by 40% via runbook automation
- Ran on-call rotation for 200+ microservices

Education
B.Tech, Computer Science
"""


# ── structure the template can typeset ──────────────────────────────────────
def test_a_job_becomes_one_entry_with_its_dates():
    """The role on the left and the dates flush right, on one line. As two
    stacked bold paragraphs there is nothing tying them together, which is what
    made these read as dumped rather than typeset."""
    tex = _md_to_latex_body("### Senior Engineer — Acme\n*2019 – 2024*\n\n- Built things.")
    assert r"\entry{Senior Engineer --- Acme}{2019 -- 2024}" in tex
    assert r"\item Built things." in tex


def test_an_empty_section_is_omitted_not_placeheld():
    """"Certifications / [Add section in cv.md]" was printed at everybody who
    had none — an unfinished-looking document on the one page that is supposed
    to argue for them."""
    tex = build_latex(CV, "ats-single")
    assert "[Add section" not in tex
    # By name, not by looking for "{{": the template's own \newcommand bodies
    # legitimately contain "{{\small ...}".
    for slot in ("NAME", "CONTACT", "SUMMARY", "SKILLS", "EXPERIENCE",
                 "PROJECTS", "EDUCATION", "CERTIFICATIONS", "ADDITIONAL"):
        assert "{{%s}}" % slot not in tex, f"{slot} was never substituted"
    assert r"\cvsection{Certifications}" not in tex, "they have none"
    assert r"\cvsection{Experience}" in tex


def test_the_sections_arrive_in_the_order_a_reader_expects():
    tex = build_latex(CV, "ats-single")
    order = [s for s in ("Summary", "Skills", "Experience", "Education")
             if f"\\cvsection{{{s}}}" in tex]
    assert order == ["Summary", "Skills", "Experience", "Education"]


# ── escaping: one bad character fails the whole document ────────────────────
@pytest.mark.parametrize("snippet", [
    "Managed a ₹4.5 crore budget",          # the one that actually broke
    "Ran a 20°C datacentre",
    "Acme™ and Beta® at €2M ARR",
    "Grew revenue 50% & cut cost 30%",
    "Wrote C++ and C# services",
    "Used a_b_c naming and #hashtags",
    "Maths: 100$ per unit, 5^2, ~approx",
    "Curly ‘quotes’ and “doubles” and an em—dash",
    r"A literal backslash \ in a path",
    "Braces {like this} in a config",
])
@needs_latex
@pytest.mark.slow
def test_a_resume_containing_awkward_punctuation_still_compiles(tmp_path, snippet):
    """Silent is what makes this dangerous: an undefined command fails the
    compile, the caller falls back to HTML, and the candidate simply gets a
    plainer resume that nobody knows was a fallback."""
    md = CV.replace("Site reliability engineer with 6 years across cloud infrastructure.",
                    snippet)
    tex_path = tmp_path / "cv.tex"
    tex_path.write_text(build_latex(md, "ats-single"), encoding="utf-8")
    ok, err, _engine = compile_tex(str(tex_path), str(tmp_path / "cv.pdf"))
    assert ok, f"{snippet!r} broke the compile: {err}"


@needs_latex
@pytest.mark.slow
def test_the_real_thing_compiles_and_reads_back(tmp_path):
    """The whole point: a PDF whose text extracts in reading order, with the
    section headings an ATS matches on."""
    pytest.importorskip("pypdf")
    from pypdf import PdfReader

    tex_path = tmp_path / "cv.tex"
    tex_path.write_text(build_latex(CV, "ats-single"), encoding="utf-8")
    ok, err, _e = compile_tex(str(tex_path), str(tmp_path / "cv.pdf"))
    assert ok, err

    text = PdfReader(str(tmp_path / "cv.pdf")).pages[0].extract_text()
    assert "Asha M" in text
    # Headings are bold mixed case, not \MakeUppercase: uppercase pairs like
    # A-T carry a wide kern, and an extractor reads a wide enough kern as a
    # space — "EDUCATION" came back as "EDUCA TION", which an ATS matching on
    # the section name does not find.
    for heading in ("Skills", "Experience", "Education"):
        assert heading in text, f"{heading} is not extractable"
    assert "Cut incident MTTR by 40%" in text
    assert text.index("Skills") < text.index("Experience"), "reading order"


@needs_latex
def test_no_ligature_survives_into_the_extracted_text(tmp_path):
    """A ligature is one glyph for "fi", so an extractor reads "Proficient" as
    "Pro<fi>cient" and a keyword scanner looking for "proficient" scores a
    miss. Real output from this repo contained "Proﬁcient" and "Oﬃces"."""
    pytest.importorskip("pypdf")
    from pypdf import PdfReader

    md = CV.replace("Kubernetes, Terraform, AWS, Python",
                    "Proficient in office workflows, fluent in difficult stacks")
    tex_path = tmp_path / "cv.tex"
    tex_path.write_text(build_latex(md, "ats-single"), encoding="utf-8")
    ok, err, _e = compile_tex(str(tex_path), str(tmp_path / "cv.pdf"))
    assert ok, err

    text = PdfReader(str(tmp_path / "cv.pdf")).pages[0].extract_text()
    assert "Proficient" in text and "office" in text and "difficult" in text
    for lig in ("ﬁ", "ﬂ", "ﬃ", "ﬄ"):
        assert lig not in text, f"ligature {lig!r} reached the extracted text"


# ── it degrades rather than breaking ────────────────────────────────────────
def test_a_missing_engine_is_reported_not_raised(tmp_path, monkeypatch):
    """The caller has an HTML fallback and a candidate with a plainer resume
    beats a candidate with none. This must never raise."""
    monkeypatch.setattr("cv.latex_builder.LATEX_ENGINES", ())
    ok, err, engine = compile_tex(str(tmp_path / "x.tex"), str(tmp_path / "x.pdf"))
    assert ok is False and engine is None and err is None


@needs_latex
@pytest.mark.slow
def test_a_document_that_cannot_compile_returns_its_error(tmp_path):
    """"LaTeX failed" with no detail is unactionable when it happens to one
    person's CV and nobody else's."""
    bad = tmp_path / "bad.tex"
    bad.write_text(r"\documentclass{article}\begin{document}\undefinedcmd\end{document}")
    ok, err, _e = compile_tex(str(bad), str(tmp_path / "bad.pdf"))
    assert ok is False
    assert err and "undefined" in err.lower()


@needs_latex
@pytest.mark.parametrize("template_id", [t.id for t in __import__(
    "cv.templates", fromlist=["CV_TEMPLATES"]).CV_TEMPLATES])
@pytest.mark.slow
def test_every_registered_template_compiles(tmp_path, template_id):
    """A registered template that cannot compile is worse than one that does
    not exist: the caller falls back to HTML and nobody is told.

    Historically this caught a class of bug that no longer has anywhere to
    hide: each template carried its own preamble, so a macro defined in one
    and used by all of them (`\\entry`) broke eleven at once, and
    `awesome-inspired` declared `\\titlerule` with a mandatory argument while
    calling it as `\\titlerule[1.2pt]`. Both now come from the one shared
    preamble in `cv/latex_layout.py`.
    """
    tex_path = tmp_path / f"{template_id}.tex"
    tex_path.write_text(build_latex(CV, template_id), encoding="utf-8")
    ok, err, _e = compile_tex(str(tex_path), str(tmp_path / f"{template_id}.pdf"))
    assert ok, f"{template_id} does not compile: {err}"


@pytest.mark.parametrize("heading,what,when", [
    ("Wipro - Senior Software Engineer (2019-2026)",
     "Wipro - Senior Software Engineer", "2019-2026"),
    ("Infosys — Software Engineer (Jul '22 to Dec '23)",
     "Infosys — Software Engineer", "Jul '22 to Dec '23"),
    ("Senior Engineer — Acme", "Senior Engineer — Acme", ""),
    ("B.E. Computer Science, Anna University, 2017",
     "B.E. Computer Science, Anna University, 2017", ""),   # one year, not a range
])
def test_dates_are_lifted_out_of_a_role_heading(heading, what, when):
    """So the timeline flushes right and a reader scans it down one edge.

    Needed twice over: a resume writes the dates inside the title as often as
    on their own line, and the tailoring model puts them back into the title
    while rewriting even when the normaliser had split them out.
    """
    from cv.latex_builder import _split_when

    assert _split_when(heading) == (what, when)
