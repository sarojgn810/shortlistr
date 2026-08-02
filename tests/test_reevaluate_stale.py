"""Repairing evaluations that fell back to the heuristic.

A template eval is what you get when the AI helper was unreachable — a
résumé/JD word overlap instead of a judgement. It is stored exactly like a real
one, so once the outage passes nothing marks the score as untrustworthy and
there is no way to find the affected rows.

This is not hypothetical: a leftover Ollama model tag (`qwen2.5:0.5b`) was being
sent to Groq, which 404s. 101 of 167 stored evaluations were silent heuristic
fallbacks. The tag was fixed days later and every one of those scores stayed.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))


@pytest.fixture
def isolated(monkeypatch):
    tmp = tempfile.mkdtemp()
    import config
    import store.db as db_mod

    monkeypatch.setattr(config, "DATA_DIR", tmp)
    monkeypatch.setattr(db_mod, "DATA_DIR", tmp)
    monkeypatch.setattr(db_mod, "DB_PATH", os.path.join(tmp, "shortlistr.db"))
    monkeypatch.setattr(db_mod, "LEGACY_DB_PATH", os.path.join(tmp, "autojob.db"))
    db_mod.init_db()
    return tmp


def _job(conn, jid: str) -> None:
    conn.execute(
        "INSERT INTO jobs (id, url, source, company, title, jd_text) "
        "VALUES (?, ?, 'test', 'Acme', 'SRE', 'kubernetes on-call')",
        (jid, f"https://x.test/{jid}"),
    )


def _eval(conn, jid: str, *, template: bool, score: float = 4.0) -> None:
    conn.execute(
        "INSERT INTO eval_results (job_id, schema_version, score, legitimacy, result_json) "
        "VALUES (?, 1, ?, 'ok', ?)",
        (jid, score, json.dumps({
            "score": score, "template_only": template,
            "eval_mode": "template" if template else "llm",
            "blocks": {"A": "x"},
        })),
    )


# ── finding them ─────────────────────────────────────────────────────────────

def test_only_template_evaluations_are_listed(isolated):
    from scheduler.scan_scheduler import stale_template_evals
    from store import db as store

    with store.db() as conn:
        for jid, tmpl in (("a", True), ("b", False), ("c", True)):
            _job(conn, jid)
            _eval(conn, jid, template=tmpl)

    assert sorted(stale_template_evals()) == ["a", "c"]


def test_a_job_re_evaluated_since_is_no_longer_stale(isolated):
    """Only the newest evaluation counts — an old template one is history."""
    from scheduler.scan_scheduler import stale_template_evals
    from store import db as store

    with store.db() as conn:
        _job(conn, "a")
        _eval(conn, "a", template=True)     # the outage
        _eval(conn, "a", template=False)    # repaired since

    assert stale_template_evals() == []


def test_a_job_that_regressed_is_stale_again(isolated):
    from scheduler.scan_scheduler import stale_template_evals
    from store import db as store

    with store.db() as conn:
        _job(conn, "a")
        _eval(conn, "a", template=False)
        _eval(conn, "a", template=True)

    assert stale_template_evals() == ["a"]


def test_no_evaluations_is_not_an_error(isolated):
    from scheduler.scan_scheduler import stale_template_evals

    assert stale_template_evals() == []


# ── repairing them ───────────────────────────────────────────────────────────

def test_repair_refuses_to_run_without_a_provider(isolated, monkeypatch):
    """Rewriting a heuristic result with another one would reset the timestamp
    and hide the problem instead of fixing it."""
    import scheduler.scan_scheduler as sched
    from store import db as store

    with store.db() as conn:
        _job(conn, "a")
        _eval(conn, "a", template=True)

    monkeypatch.setattr("llm.get_llm", lambda *a, **k: None)
    called = []
    monkeypatch.setattr("eval.service.evaluate_job_text",
                        lambda *a, **k: called.append(1))

    res = sched.reevaluate_stale()
    assert res["skipped_no_provider"] == 1
    assert res["repaired"] == 0
    assert res["candidates"] == 1, "it should still report what needs repair"
    assert not called, "evaluated anyway with no provider"


def test_repair_reruns_each_stale_evaluation(isolated, monkeypatch):
    import scheduler.scan_scheduler as sched
    from store import db as store

    with store.db() as conn:
        for jid in ("a", "b"):
            _job(conn, jid)
            _eval(conn, jid, template=True)

    monkeypatch.setattr("llm.get_llm", lambda *a, **k: type("P", (), {
        "is_available": lambda self: True})())

    seen = []

    class Result:
        eval_mode = "llm"

    def fake_eval(jd, **kw):
        seen.append(kw.get("job_id"))
        return Result()

    monkeypatch.setattr("eval.service.evaluate_job_text", fake_eval)
    res = sched.reevaluate_stale()
    assert sorted(seen) == ["a", "b"]
    assert res["repaired"] == 2 and res["still_template"] == 0


def test_a_job_that_stays_template_is_counted_separately(isolated, monkeypatch):
    """If it falls back again the run must say so, not report a clean repair."""
    import scheduler.scan_scheduler as sched
    from store import db as store

    with store.db() as conn:
        _job(conn, "a")
        _eval(conn, "a", template=True)

    monkeypatch.setattr("llm.get_llm", lambda *a, **k: type("P", (), {
        "is_available": lambda self: True})())

    class Result:
        eval_mode = "template"

    monkeypatch.setattr("eval.service.evaluate_job_text", lambda jd, **kw: Result())
    res = sched.reevaluate_stale()
    assert res["repaired"] == 0 and res["still_template"] == 1


def test_one_failing_job_does_not_stop_the_rest(isolated, monkeypatch):
    import scheduler.scan_scheduler as sched
    from store import db as store

    with store.db() as conn:
        for jid in ("a", "b", "c"):
            _job(conn, jid)
            _eval(conn, jid, template=True)

    monkeypatch.setattr("llm.get_llm", lambda *a, **k: type("P", (), {
        "is_available": lambda self: True})())

    class Result:
        eval_mode = "llm"

    def flaky(jd, **kw):
        if kw.get("job_id") == "b":
            raise RuntimeError("provider hiccup")
        return Result()

    monkeypatch.setattr("eval.service.evaluate_job_text", flaky)
    assert sched.reevaluate_stale()["repaired"] == 2
