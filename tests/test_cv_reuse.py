"""An up-to-date CV PDF is reused instead of re-rendered.

Rendering launches a whole Chromium per call — measured at 11.5s, which was 78%
of the time to build a prep bundle, and it was paid again every time the same
job was opened to produce a byte-identical file. cv.md and the template
preference are the only inputs, so if neither moved since the PDF was written,
re-rendering cannot change it.

Prep on a job whose CV is current: 19.5s -> 2.5s.
"""

from __future__ import annotations

import os
import sys
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))


@pytest.fixture
def paths(monkeypatch, tmp_path):
    import processors.generate_cv as gc

    cv_md = tmp_path / "cv.md"
    cv_md.write_text("# Alex Candidate\n\nSRE with 9 years.\n")
    profile = tmp_path / "profile.yml"
    profile.write_text("filters: {}\n")
    out = tmp_path / "output"
    out.mkdir()

    monkeypatch.setattr(gc, "CV_MD_PATH", str(cv_md))
    monkeypatch.setattr(gc, "PROFILE_PATH", str(profile))
    monkeypatch.setattr(gc, "OUTPUT_DIR", str(out))
    return {"cv": cv_md, "profile": profile, "out": out, "gc": gc}


def _pdf(paths, name="pdf") -> str:
    p = paths["out"] / f"{name}.pdf"
    p.write_bytes(b"%PDF-1.4" + b"x" * 4096)
    return str(p)


def test_a_fresh_pdf_is_considered_current(paths):
    assert paths["gc"]._is_current(_pdf(paths)) is True


def test_a_missing_pdf_is_not_current(paths):
    assert paths["gc"]._is_current(str(paths["out"] / "nope.pdf")) is False


def test_a_truncated_pdf_is_not_current(paths):
    """A few bytes on disk is a failed render, not a document to hand an employer."""
    stub = paths["out"] / "tiny.pdf"
    stub.write_bytes(b"%PDF")
    assert paths["gc"]._is_current(str(stub)) is False


def test_editing_the_cv_invalidates_the_pdf(paths):
    """The whole point: a changed résumé must not keep serving the old PDF."""
    pdf = _pdf(paths)
    time.sleep(0.01)
    paths["cv"].write_text("# Alex Candidate\n\nNow with Kubernetes.\n")
    assert paths["gc"]._is_current(pdf) is False


def test_changing_the_template_preference_invalidates_the_pdf(paths):
    pdf = _pdf(paths)
    time.sleep(0.01)
    paths["profile"].write_text("cv: {template_id: modern}\n")
    assert paths["gc"]._is_current(pdf) is False


def test_generate_reuses_a_current_pdf_without_rendering(paths, monkeypatch):
    gc = paths["gc"]
    rendered = []
    monkeypatch.setattr(gc, "_cv_preferences", lambda: ("ats-single", "auto"))
    monkeypatch.setattr("cv.latex_builder.latex_available", lambda: False)
    def fake_render(html, pdf_path, **k):
        rendered.append(1)
        with open(pdf_path, "wb") as f:      # a real render leaves a real file
            f.write(b"%PDF-1.4" + b"x" * 4096)

    monkeypatch.setattr("generate_pdf.generate_pdf_from_html", fake_render)

    job = {"company": "Acme", "id": "job1", "url": "https://x.test/1"}
    first = gc.generate_cv_for_job(job)
    assert rendered, "the first call should actually render"

    rendered.clear()
    second = gc.generate_cv_for_job(job)
    assert second.get("reused") is True
    assert not rendered, "re-rendered a PDF that was already current"
    assert second["path"] == first["path"]


def test_force_re_renders_even_when_current(paths, monkeypatch):
    gc = paths["gc"]
    rendered = []
    monkeypatch.setattr(gc, "_cv_preferences", lambda: ("ats-single", "auto"))
    monkeypatch.setattr("cv.latex_builder.latex_available", lambda: False)
    def fake_render(html, pdf_path, **k):
        rendered.append(1)
        with open(pdf_path, "wb") as f:
            f.write(b"%PDF-1.4" + b"x" * 4096)

    monkeypatch.setattr("generate_pdf.generate_pdf_from_html", fake_render)

    job = {"company": "Acme", "id": "job1", "url": "https://x.test/1"}
    gc.generate_cv_for_job(job)
    rendered.clear()
    out = gc.generate_cv_for_job(job, force=True)
    assert rendered, "force did not re-render"
    assert not out.get("reused")


def test_an_empty_cv_still_reports_the_real_problem(paths):
    """Reuse must not mask "you have not finished onboarding"."""
    paths["cv"].write_text("   \n")
    out = paths["gc"].generate_cv_for_job({"company": "Acme", "id": "j"})
    assert out["success"] is False
    assert "cv.md is empty" in out["error"]
