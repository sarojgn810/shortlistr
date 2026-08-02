"""Company/role interview research for prep guides."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "automation"))

from prep.research import _extract_questions, research_interview  # noqa: E402
from processors.generate_prep import _build_prep_doc  # noqa: E402


def test_extract_questions_from_snippets():
    blob = (
        "Interview process. How do you design an observability stack for payments? "
        "1. Tell me about a hard production incident you owned?\n"
        "Also: Walk me through your on-call philosophy?"
    )
    qs = _extract_questions(blob)
    assert any("observability" in q.lower() for q in qs)
    assert any("incident" in q.lower() or "on-call" in q.lower() for q in qs)


def test_research_without_hits_is_fallback(monkeypatch):
    monkeypatch.setattr("prep.research.web_organic", lambda *a, **k: [])
    out = research_interview("Stripe", "Staff SRE")
    assert out["mode"] == "fallback"
    assert out["questions"] == []
    assert out["notes"]


def test_research_with_free_web_search(monkeypatch):
    def fake_organic(query, *, num=6):
        return [
            {
                "title": "Stripe interview process",
                "link": "https://example.com/stripe-loop",
                "snippet": (
                    "Stripe interviews usually include a recruiter screen, then a "
                    "technical loop. How do you approach payment system reliability?"
                ),
                "query": query,
            }
        ]

    monkeypatch.setattr("prep.research.web_organic", fake_organic)
    out = research_interview("Stripe", "Site Reliability Engineer")
    assert out["mode"] == "researched"
    assert out["sources"]
    assert out["process"] or out["questions"]
    assert "free search" in " ".join(out["notes"]).lower()


def test_build_prep_differs_by_company(monkeypatch):
    """Guides must not be identical clones that only swap the company name."""

    def organic_for(query, *, num=6):
        if "Datadog" in query:
            return [
                {
                    "title": "Datadog SRE interview",
                    "link": "https://example.com/dd",
                    "snippet": "How do you define SLOs for a metrics ingest pipeline?",
                }
            ]
        return [
            {
                "title": "Notion platform interview",
                "link": "https://example.com/notion",
                "snippet": "How would you design collaborative document sync at scale?",
            }
        ]

    monkeypatch.setattr("prep.research.web_organic", organic_for)
    monkeypatch.setattr("prep.research.draft_star_answers", lambda *a, **k: {})

    cv = "# Ada\n\n## Experience\n- Built Prometheus stacks for payments.\n"
    a = _build_prep_doc(
        {"company": "Datadog", "title": "SRE", "job_id": "a" * 16, "jd_text": "SRE role"},
        cv,
    )
    b = _build_prep_doc(
        {
            "company": "Notion",
            "title": "Platform Engineer",
            "job_id": "b" * 16,
            "jd_text": "Platform role",
        },
        cv,
    )
    assert "Datadog" in a and "Notion" in b
    assert "metrics ingest" in a.lower() or "slos" in a.lower()
    assert "document sync" in b.lower() or "collaborative" in b.lower()
    assert a != b


def test_unstamped_legacy_prep_ignored(tmp_path, monkeypatch):
    import config
    from prep.ownership import load_owned_prep

    prep = tmp_path / "interview-prep"
    prep.mkdir()
    monkeypatch.setattr(config, "PREP_DIR", str(prep), raising=False)
    monkeypatch.setattr(config, "CANDIDATE", {"email": "ada@example.com", "name": "Ada"}, raising=False)

    legacy = prep / "Acme-SRE-2026-01-01.md"
    legacy.write_text(
        "# Interview Prep — Acme\n**Prepared for:** Previous Owner\n"
        "## Your Proof Points\n- Personal secret story\n"
        "**Job URL:** https://example.com/jobs/1\n",
        encoding="utf-8",
    )
    path, content = load_owned_prep("cccccccccccccccc", url="https://example.com/jobs/1")
    assert path is None
    assert content is None
