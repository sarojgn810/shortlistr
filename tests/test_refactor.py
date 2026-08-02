"""Tests for refactor: env loading, LLM status, shared queries."""

from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))


def test_latest_eval_join_exported():
    from store.queries import LATEST_EVAL_JOIN, LATEST_EVAL_JOIN_ON_APPLICATIONS

    assert "eval_results" in LATEST_EVAL_JOIN
    assert "ev.job_id" in LATEST_EVAL_JOIN
    assert "ev.job_id = a.job_id" in LATEST_EVAL_JOIN_ON_APPLICATIONS


def test_llm_status_shape():
    from llm.status import llm_status

    st = llm_status()
    assert "provider" in st
    assert "available" in st
    assert "mode" in st
    assert st["mode"] in ("llm", "template")
    assert st["features"]["tool_calling"] is False
    assert st["features"]["rag"] is False
    assert st["env_var"] == "SHORTLISTR_LLM_API_KEY"
