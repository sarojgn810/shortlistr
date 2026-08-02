"""Prep says what to study, and in what order.

Two halves with different failure modes. The path is derived from the job
description's own requirements, so it works offline. The reading list needs web
search, and free DuckDuckGo is frequently bot-challenged (HTTP 202) — so when
it is empty the document says why instead of printing a bare heading.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "automation"))


# ── what counts as learning material ─────────────────────────────────────────

def test_a_job_advert_is_not_study_material():
    """A board answering "SRE learning path" is another listing, not a resource."""
    from prep.research import _looks_like_learning

    for link in (
        "https://www.indeed.com/q-sre-jobs.html",
        "https://www.naukri.com/sre-jobs",
        "https://www.linkedin.com/jobs/view/12345",
        "https://glassdoor.com/Jobs/sre.htm",
    ):
        assert not _looks_like_learning({"link": link}), link


def test_teaching_hosts_are_kept():
    from prep.research import _looks_like_learning

    for link in (
        "https://sre.google/sre-book/table-of-contents/",
        "https://kubernetes.io/docs/concepts/",
        "https://opentelemetry.io/docs/",
        "https://github.com/someone/sre-interview-prep",
    ):
        assert _looks_like_learning({"link": link}), link


def test_a_non_http_link_is_rejected():
    from prep.research import _looks_like_learning

    assert not _looks_like_learning({"link": "javascript:void(0)"})
    assert not _looks_like_learning({})


# ── the path ─────────────────────────────────────────────────────────────────

def test_the_path_is_built_even_with_no_search(monkeypatch):
    """DuckDuckGo is bot-challenged most of the time; the plan must survive it."""
    from prep import research

    monkeypatch.setattr(research, "web_organic", lambda *a, **k: [])
    out = research.research_learning_resources("Site Reliability Engineer",
                                               skills=["Kubernetes", "Terraform"])
    assert out["resources"] == []
    assert len(out["path"]) >= 3
    assert any("Kubernetes" in step for step in out["path"]), out["path"]


def test_the_path_names_the_role():
    from prep import research

    out = research.research_learning_resources("Staff SRE | Observability")
    # The role is trimmed at the separator, not pasted in whole.
    assert any("Staff SRE" in s for s in out["path"])


def test_resources_are_deduped_and_capped(monkeypatch):
    from prep import research

    hit = {"link": "https://kubernetes.io/docs/", "title": "K8s docs", "snippet": "s"}
    monkeypatch.setattr(research, "web_organic", lambda *a, **k: [hit] * 10)
    out = research.research_learning_resources("SRE", skills=["Kubernetes"], max_items=4)
    assert len(out["resources"]) == 1, "the same link was added more than once"


def test_listings_are_filtered_out_of_results(monkeypatch):
    from prep import research

    monkeypatch.setattr(research, "web_organic", lambda *a, **k: [
        {"link": "https://www.indeed.com/q-sre-jobs.html", "title": "SRE jobs"},
        {"link": "https://sre.google/workbook/", "title": "SRE Workbook"},
    ])
    out = research.research_learning_resources("SRE")
    assert [r["link"] for r in out["resources"]] == ["https://sre.google/workbook/"]


def test_a_search_failure_is_not_fatal(monkeypatch):
    from prep import research

    def boom(*a, **k):
        raise RuntimeError("search is down")

    monkeypatch.setattr(research, "web_organic", boom)
    try:
        out = research.research_learning_resources("SRE")
    except RuntimeError:
        raise AssertionError("a dead search backend took prep down with it")
    assert out["resources"] == []
