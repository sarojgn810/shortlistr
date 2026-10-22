"""Offline checks for the optional LinkedIn jobs actor."""

from __future__ import annotations

import importlib.util
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADAPTER_PATH = os.path.join(ROOT, "automation", "sources", "linkedin_jobs_adapter.py")
BOARDS_PATH = os.path.join(ROOT, "automation", "sources", "apify_boards.py")


def _load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


adapter = _load("shortlistr_linkedin_jobs_adapter", ADAPTER_PATH)
sources_pkg = types.ModuleType("sources")
sources_pkg.linkedin_jobs_adapter = adapter
sys.modules.setdefault("sources", sources_pkg)
sys.modules["sources.linkedin_jobs_adapter"] = adapter
boards = _load("shortlistr_apify_boards", BOARDS_PATH)


def test_default_linkedin_input_stays_on_the_current_actor(monkeypatch):
    monkeypatch.delenv("SHORTLISTR_LINKEDIN_JOBS_ACTOR", raising=False)
    assert adapter.resolve_linkedin_actor({}, None) == "valig/linkedin-jobs-scraper"
    body = boards._linkedin_input(
        "SRE",
        "Bengaluru",
        limit=40,
        experience=5,
        wants_remote=True,
        cfg={},
    )
    assert body["title"] == "SRE"
    assert body["remote"] == ["1", "2", "3"]
    assert "keyword" not in body


def test_optional_actor_sends_a_keyword_body_and_keeps_job_rows(monkeypatch):
    monkeypatch.setenv("SHORTLISTR_LINKEDIN_JOBS_ACTOR", adapter.OPTIONAL_LINKEDIN_JOBS_ACTOR)
    assert (
        adapter.resolve_linkedin_actor(
            {"linkedin_actor": "valig/linkedin-jobs-scraper"},
            adapter.OPTIONAL_LINKEDIN_JOBS_ACTOR,
        )
        == adapter.OPTIONAL_LINKEDIN_JOBS_ACTOR
    )
    body = boards._linkedin_input(
        "Example role",
        "Remote",
        limit=400,
        experience=1,
        wants_remote=True,
        cfg={"linkedin_actor": "valig/linkedin-jobs-scraper"},
    )
    assert body == {
        "keyword": "Example role",
        "location": "Remote",
        "maxJobs": 100,
        "remote": True,
    }
    city = adapter.optional_linkedin_jobs_input(
        "Example role",
        "Bengaluru",
        limit=40,
        wants_remote=True,
    )
    assert city["remote"] is False

    rows = adapter.accept_linkedin_job_items(
        [
            {"result_type": "error", "title": "skip"},
            {
                "result_type": "job",
                "title": "Example role",
                "companyName": "Example Co",
                "jobUrl": "https://www.linkedin.com/jobs/view/1",
                "location": "Example City",
                "description": "",
                "seniorityLevel": "Mid-Senior",
                "salaryMin": 1,
                "salaryMax": 2,
                "salaryCurrency": "USD",
            },
        ]
    )
    assert len(rows) == 1
    assert rows[0]["seniority"] == "Mid-Senior"
    assert rows[0]["salary_min"] == 1
    assert rows[0]["jobUrl"] == "https://www.linkedin.com/jobs/view/1"
