"""Shared pytest fixtures — deterministic tests without live LLM calls."""

from __future__ import annotations

import os
import tempfile

import pytest


@pytest.fixture(autouse=True)
def isolate_data_dir(monkeypatch):
    """Redirect DATA_DIR / DB_PATH / OUTPUT_DIR to a temp dir for EVERY test, so
    nothing (e.g. EvalService persisting source='eval' jobs) ever writes to the
    real data/shortlistr.db. Tests with their own isolated_data_dir fixture still
    override this (their fixture runs after autouse)."""
    tmp = tempfile.mkdtemp(prefix="shortlistr-test-")
    out = os.path.join(tmp, "output")
    os.makedirs(out, exist_ok=True)
    try:
        import sys

        import config
        import store.db as db_mod

        cv_md = os.path.join(tmp, "cv.md")
        monkeypatch.setattr(config, "DATA_DIR", tmp, raising=False)
        monkeypatch.setattr(config, "OUTPUT_DIR", out, raising=False)
        monkeypatch.setattr(config, "CV_MD_PATH", cv_md, raising=False)
        monkeypatch.setattr(db_mod, "DATA_DIR", tmp, raising=False)
        monkeypatch.setattr(db_mod, "DB_PATH", os.path.join(tmp, "shortlistr.db"), raising=False)
        # Modules that imported CV_MD_PATH *by value* keep their own reference, so
        # patch those too — otherwise a CV test writes/deletes the real repo-root cv.md.
        for _modname in ("eval.service", "processors.generate_cv", "cv.latex_builder", "cv.ingest"):
            _m = sys.modules.get(_modname)
            if _m is not None and hasattr(_m, "CV_MD_PATH"):
                monkeypatch.setattr(_m, "CV_MD_PATH", cv_md, raising=False)
    except Exception:
        pass


@pytest.fixture(autouse=True)
def disable_llm_for_tests(monkeypatch):
    """Eval tests use heuristic/template path; never call OpenAI/Anthropic in CI."""
    monkeypatch.setenv("SHORTLISTR_LLM_API_KEY", "")
    try:
        import config

        monkeypatch.setitem(config.LLM_CONFIG, "provider", "none")
        monkeypatch.setitem(config.LLM_CONFIG, "api_key", "")
    except Exception:
        pass
    try:
        import llm

        llm._cached_llm = None
        llm._cache_loaded = False
    except Exception:
        pass
