"""Reaching the application form when the posting opens on a description.

Most job URLs land on a description page whose form only exists after clicking
Apply. `_reveal_application_form` handled exactly one ATS — everything else
returned immediately after a scroll — so on Workday, Lever, Ashby or a plain
careers page the run found no fields, filled nothing, and the browser closed on
a posting the user had already approved.

The click is gated on there being no form yet, and that gate is the safety
property, not an optimisation: "Apply now" is navigation on a listing page and a
submit control on a completed form. Same words, opposite sides of the one line
this tool must never cross. If anything fillable is on screen, nothing is
clicked.

These run real pages through Playwright and skip when it is not installed.
"""

from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))

from apply.ats_fill import _APPLY_NAV_PATTERNS, playwright_ready


def _skip_without_browser():
    ok, why = playwright_ready()
    if not ok:
        pytest.skip(f"Playwright unavailable: {why}")


DESCRIPTION_PAGE = """<html><body>
<h1>Site Reliability Engineer</h1>
<p>Kubernetes, Terraform, on-call.</p>
<input type="text" placeholder="Search jobs">
<a href="form.html">Apply now</a>
<button>Save job</button>
</body></html>"""

FORM_PAGE = """<html><body><h2>Application</h2><form>
<label>First name<input type="text" name="first_name"></label>
<label>Last name<input type="text" name="last_name"></label>
<label>Email<input type="email" name="email"></label>
<input type="file" name="resume">
<button type="submit">Submit application</button>
</form></body></html>"""

# The trap: the submit control itself says "Apply now".
TRAP_PAGE = """<html><body><h2>Apply</h2>
<form action="submitted.html" method="get">
<label>Email<input type="email" name="email"></label>
<label>First name<input type="text" name="first_name"></label>
<button type="submit">Apply now</button>
</form></body></html>"""

SUBMITTED_PAGE = "<html><body><h1>APPLICATION WAS SUBMITTED</h1></body></html>"


@pytest.fixture
def site(tmp_path):
    (tmp_path / "job.html").write_text(DESCRIPTION_PAGE)
    (tmp_path / "form.html").write_text(FORM_PAGE)
    (tmp_path / "trap.html").write_text(TRAP_PAGE)
    (tmp_path / "submitted.html").write_text(SUBMITTED_PAGE)
    return lambda name: (tmp_path / name).as_uri()


# ── which words mean "go to the form" ────────────────────────────────────────

def test_apply_wording_is_recognised():
    for text in ("Apply", "Apply now", "Apply for this job", "Apply online",
                 "Start application", "I'm interested"):
        assert _APPLY_NAV_PATTERNS.search(text), text


def test_submitting_words_are_not_navigation():
    for text in ("Submit application", "Send application", "Complete application"):
        assert not _APPLY_NAV_PATTERNS.search(text), text


def test_unrelated_buttons_are_not_navigation():
    for text in ("Save job", "Share", "Back to search", "Sign in"):
        assert not _APPLY_NAV_PATTERNS.search(text), text


# ── the behaviour ────────────────────────────────────────────────────────────

def test_a_description_page_reaches_the_form(site):
    """The reported bug: the link opened the page with the Apply button."""
    _skip_without_browser()
    from apply.ats_fill import fill_application_form

    report = fill_application_form(site("job.html"), company="Acme", headless=True)
    assert report["form_detected"] is True
    assert "email" in report["filled"], report
    assert report["ready_for_user_review"] is True


def test_landing_on_the_form_does_not_navigate_away(site):
    _skip_without_browser()
    from apply.ats_fill import fill_application_form

    report = fill_application_form(site("form.html"), company="Acme", headless=True)
    assert "email" in report["filled"]
    assert "first_name" in report["filled"]


def test_a_submit_button_reading_apply_now_is_never_clicked(site):
    """The safety property. If this regresses, the tool submits applications."""
    _skip_without_browser()
    from apply.ats_fill import fill_application_form

    report = fill_application_form(site("trap.html"), company="Acme", headless=True)
    assert "email" in report["filled"], "should still fill the form"
    assert "submitted.html" not in str(report.get("url") or ""), (
        "apply-assist submitted an application"
    )


def test_a_page_with_no_form_reports_that_rather_than_failing(site, tmp_path):
    """Nothing to fill is a finding to report, not an exception."""
    _skip_without_browser()
    from apply.ats_fill import fill_application_form

    (tmp_path / "empty.html").write_text("<html><body><p>Role closed.</p></body></html>")
    report = fill_application_form((tmp_path / "empty.html").as_uri(),
                                   company="Acme", headless=True)
    assert report["form_detected"] is False
    assert report["ready_for_user_review"] is False
    assert report["filled"] == []
