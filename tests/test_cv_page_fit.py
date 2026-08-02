"""Page count is a promise, so it is measured rather than hoped for.

The HTML preview used to "fit to one page" by shrinking the text with a script
and then clipping whatever was still over — content disappeared off the bottom
of the sheet and nothing said so. The LaTeX path compiles, counts the pages in
the actual PDF, and changes the layout density until the count is right.

Two things must hold: a résumé that fits gets the *roomiest* layout that fits
(not the first one tried), and one that cannot fit is reported as not fitting
instead of being crushed or silently truncated.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "automation"))

import pytest

from cv.latex_builder import fit_to_pages, latex_available, pdf_page_count
from cv.latex_layout import DENSITY_LADDER, build_preamble, density_by_name

ENGINE = latex_available()
needs_latex = pytest.mark.skipif(not ENGINE, reason="no LaTeX engine installed")

SHORT_CV = """# Asha M
asha@example.com | +91 90000 00000

## Summary
Site reliability engineer with 6 years across cloud infrastructure.

## Skills
Kubernetes, Terraform, AWS, Python

## Experience

### Site Reliability Engineer 2021 – Present
AcmeCloud Bengaluru, India
- Cut incident MTTR by 40% via runbook automation.
- Ran the on-call rotation for 200+ microservices.

## Education
B.Tech, Computer Science, Anna University 2013 – 2017
"""

_ROLE = """
### Site Reliability Engineer {n}
BigCorp {n} Bengaluru, India
- Designed and operated a multi-region Kubernetes platform serving several
  hundred services, holding a 99.9% availability target through peak season.
- Built the alerting and on-call practice from scratch, cutting pages per week
  by more than half while improving time to detect.
- Automated the release pipeline end to end, taking deploys from weekly and
  manual to on-demand and self-service for every team.
- Led capacity planning and cost work that returned a quarter of the cloud
  spend without touching the availability target.
"""


def _long_cv(roles: int = 8) -> str:
    body = "".join(_ROLE.format(n=i) for i in range(roles))
    return SHORT_CV.replace("## Education", f"{body}\n## Education")


# ── the ladder itself ───────────────────────────────────────────────────────
def test_the_ladder_runs_roomiest_to_densest():
    """The search walks it by index in both directions, so the ordering is
    load-bearing rather than cosmetic."""
    margins = [float(d.margin.rstrip("cm")) for d in DENSITY_LADDER]
    assert margins == sorted(margins, reverse=True)
    leading = [float(d.linespread) for d in DENSITY_LADDER]
    assert leading[0] > leading[-1]


def test_every_rung_builds_a_preamble_with_its_own_geometry():
    for rung in DENSITY_LADDER:
        preamble = build_preamble(rung)
        assert rung.margin in preamble
        assert rf"\linespread{{{rung.linespread}}}" in preamble
        # ATS hardening is not per-template and must be present on every rung.
        assert "Ligatures      = NoCommon" in preamble
        assert r"\hyphenpenalty=10000" in preamble
        assert r"\widowpenalty=10000" in preamble


def test_a_template_can_cap_how_far_it_is_squeezed():
    """Modern Minimal separates sections with whitespace alone, so past a
    point tightening it stops meaning "denser" and starts meaning "wrong"."""
    assert density_by_name("snug") < density_by_name("tight")


# ── measured behaviour ──────────────────────────────────────────────────────
@needs_latex
@pytest.mark.slow
def test_a_short_resume_fits_one_page_and_keeps_its_whitespace(tmp_path):
    result = fit_to_pages(SHORT_CV, "ats-single",
                          str(tmp_path / "cv.tex"), str(tmp_path / "cv.pdf"),
                          page_target=1)
    assert result["ok"] and result["fitted"]
    assert result["pages"] == 1
    # It fits with room to spare, so the search should not have left it dense.
    assert result["density"] <= density_by_name("normal"), (
        f"squeezed to {result['density_name']} when it did not need to be"
    )


@needs_latex
@pytest.mark.slow
def test_a_long_resume_asked_for_two_pages_gets_exactly_two(tmp_path):
    result = fit_to_pages(_long_cv(), "ats-single",
                          str(tmp_path / "cv.tex"), str(tmp_path / "cv.pdf"),
                          page_target=2)
    assert result["ok"] and result["fitted"]
    assert result["pages"] == 2


@needs_latex
@pytest.mark.slow
def test_a_resume_that_cannot_fit_one_page_says_so(tmp_path):
    """Rather than truncating, or quietly returning four pages while the UI
    still says "single page · auto-fitted"."""
    result = fit_to_pages(_long_cv(12), "ats-single",
                          str(tmp_path / "cv.tex"), str(tmp_path / "cv.pdf"),
                          page_target=1)
    assert result["ok"]
    assert result["fitted"] is False
    assert result["pages"] > 1


@needs_latex
@pytest.mark.slow
def test_auto_settles_for_two_pages_without_crushing_the_layout(tmp_path):
    """Auto prefers one page. When that is impossible it must relax back to
    the roomiest two-page layout, not keep the densest rung it tried while
    failing to reach one page."""
    result = fit_to_pages(_long_cv(), "ats-single",
                          str(tmp_path / "cv.tex"), str(tmp_path / "cv.pdf"),
                          page_target="auto")
    assert result["ok"] and result["fitted"]
    assert result["pages"] == 2
    assert result["density"] < density_by_name("tight")


@needs_latex
@pytest.mark.slow
def test_the_tex_left_on_disk_is_the_one_that_was_compiled(tmp_path):
    """The search overwrites the .tex on every attempt. If the last attempt is
    not the winner, the downloadable LaTeX and the downloadable PDF are
    different documents."""
    tex, pdf = str(tmp_path / "cv.tex"), str(tmp_path / "cv.pdf")
    result = fit_to_pages(SHORT_CV, "ats-single", tex, pdf, page_target=1)
    chosen = DENSITY_LADDER[result["density"]]
    assert chosen.margin in open(tex, encoding="utf-8").read()
    assert pdf_page_count(pdf) == result["pages"]
