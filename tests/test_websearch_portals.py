"""Portals.yml websearch companies must feed discovery, not sit as dead config."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "automation"))


def test_websearch_company_queries_load(tmp_path):
    from portals_config import get_websearch_company_queries

    portals = tmp_path / "portals.yml"
    portals.write_text(
        """
tracked_companies:
  - name: Acme
    careers_url: https://acme.example/careers
    scan_method: websearch
    scan_query: 'site:boards.greenhouse.io/acme SRE'
    enabled: true
  - name: SilentCo
    careers_url: https://silent.example/careers
    scan_method: websearch
    enabled: true
  - name: GreenhouseOnly
    careers_url: https://job-boards.greenhouse.io/foo
    api: https://boards-api.greenhouse.io/v1/boards/foo/jobs
    enabled: true
""",
        encoding="utf-8",
    )

    queries, stats = get_websearch_company_queries(str(portals), limit=8)
    assert len(queries) == 1
    assert queries[0]["name"] == "company:Acme"
    assert "SRE" in queries[0]["query"]
    assert stats["companies"] == 2
    assert stats["skipped_no_query"] == 1
    assert stats["with_query"] == 1


def test_load_search_queries_includes_company_websearch(tmp_path, monkeypatch):
    from processors import search_discovery

    portals = tmp_path / "portals.yml"
    portals.write_text(
        """
search_queries: []
tracked_companies:
  - name: Acme
    scan_method: websearch
    scan_query: 'site:jobs.ashbyhq.com/acme "Site Reliability"'
    enabled: true
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(search_discovery, "_auto_location_queries", lambda: [])
    queries = search_discovery.load_search_queries(str(portals))
    assert any(q.get("name") == "company:Acme" for q in queries)
