"""Stub JD enrichment fills empty LinkedIn/search rows from page text."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "automation"))


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    import store.db as db_mod

    monkeypatch.setattr(db_mod, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(db_mod, "DB_PATH", str(tmp_path / "shortlistr.db"))
    yield tmp_path


def test_enrich_job_page_fills_jd(monkeypatch):
    from processors import enrich_jd
    from scrapers.browser_fetch import PageFetch

    html = """
    <html><head><title>Staff SRE</title></head><body>
    <h1>Staff Site Reliability Engineer</h1>
    <p>""" + ("Run production systems on Kubernetes with Terraform. " * 20) + """</p>
    </body></html>
    """

    monkeypatch.setattr(
        enrich_jd,
        "fetch_page",
        lambda url, allow_browser=True: PageFetch(
            url=url, html=html, final_url=url, status=200, via="requests"
        ),
    )
    result = enrich_jd.enrich_job_page(
        {"url": "https://example.com/jobs/1", "title": "", "source": "LinkedIn"}
    )
    assert result["ok"] is True
    assert "Kubernetes" in result["jd_text"]


def test_enrich_job_page_surfaces_http_error(monkeypatch):
    from processors import enrich_jd
    from scrapers.browser_fetch import PageFetch

    monkeypatch.setattr(
        enrich_jd,
        "fetch_page",
        lambda url, allow_browser=True: PageFetch(
            url=url, error="HTTP 403", status=403, via="requests"
        ),
    )
    result = enrich_jd.enrich_job_page({"url": "https://example.com/x"})
    assert result["ok"] is False
    assert "403" in result["error"]


def test_enrich_stub_jobs_updates_db(isolated, monkeypatch):
    from models.job import JobRecord
    from processors import enrich_jd
    from scrapers.browser_fetch import PageFetch
    from store import db as store

    store.init_db()
    job = JobRecord(
        url="https://www.linkedin.com/jobs/view/999",
        source="LinkedIn",
        company="Acme",
        title="Site Reliability Engineer",
        location="Bengaluru",
        jd_text="",
    )
    store.upsert_jobs([job])

    html = (
        "<html><body><h1>SRE</h1><p>"
        + ("Observability Prometheus Grafana on-call. " * 30)
        + "</p></body></html>"
    )
    monkeypatch.setattr(
        enrich_jd,
        "fetch_page",
        lambda url, allow_browser=True: PageFetch(
            url=url, html=html, final_url=url, status=200, via="requests"
        ),
    )
    result = enrich_jd.enrich_stub_jobs(
        limit=5, allow_browser=False, title_match_only=False
    )
    assert result["updated"] == 1
    with store.db() as conn:
        row = conn.execute(
            "SELECT jd_text FROM jobs WHERE id = ?", (job.job_id,)
        ).fetchone()
    assert "Prometheus" in (row["jd_text"] or "")
