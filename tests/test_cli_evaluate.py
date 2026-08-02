"""`evaluate JOB_ID=<id>` — the same work the endpoint does, with the traceback.

When an exception escapes a route handler to the ASGI layer, the response is
aborted. The API's own error handler had already built a JSON body naming the
cause, but it never reaches the browser: the client falls back to res.statusText
and prints "ApiError: Internal Server Error", which says only that something
went wrong somewhere.

That left the cause visible solely in the server console. This subcommand runs
the identical path from a terminal and prints the whole traceback, so a user can
find out what is wrong without reading their own uvicorn scrollback.
"""

from __future__ import annotations

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
    return db_mod


def _job(db_mod, jid="a1b2c3d4e5f60718"):
    with db_mod.db() as conn:
        conn.execute(
            "INSERT INTO jobs (id, url, source, company, title, jd_text) "
            "VALUES (?, ?, 'test', 'Acme', 'SRE', ?)",
            (jid, f"https://x.test/{jid}", "kubernetes terraform on-call " * 30),
        )
    return jid


def _run(*args) -> int:
    from cli import main

    return main(["evaluate", *args])


def test_usage_is_printed_without_an_id(capsys):
    assert _run() == 1
    assert "JOB_ID" in capsys.readouterr().err


def test_an_unknown_job_says_so(isolated, capsys):
    assert _run("JOB_ID=ffffffffffffffff") == 1
    assert "No job" in capsys.readouterr().err


def test_a_bare_id_is_accepted(isolated, capsys, monkeypatch):
    """Typing the id without the JOB_ID= prefix is the obvious thing to try."""
    jid = _job(isolated)
    monkeypatch.setattr("eval.service.evaluate_job_text",
                        lambda *a, **k: type("R", (), {
                            "score": 4.0, "eval_mode": "llm", "blocks": {"A": "x"}})())

    assert _run(jid) == 0
    assert "score" in capsys.readouterr().out


def test_the_mode_is_reported(isolated, capsys, monkeypatch):
    """Whether an LLM ran at all is the first thing worth knowing."""
    jid = _job(isolated)
    monkeypatch.setattr("eval.service.evaluate_job_text",
                        lambda *a, **k: type("R", (), {
                            "score": 2.6, "eval_mode": "template", "blocks": {}})())

    assert _run(f"JOB_ID={jid}") == 0
    out = capsys.readouterr().out
    assert "template" in out
    assert "Basic score" in out, "a template result should say what that means"


def test_a_failure_prints_the_traceback(isolated, capsys, monkeypatch):
    """The whole point — a 500 in the browser tells you nothing."""
    jid = _job(isolated)

    def boom(*a, **k):
        raise RuntimeError("ollama refused the connection")

    monkeypatch.setattr("eval.service.evaluate_job_text", boom)

    assert _run(f"JOB_ID={jid}") == 1
    err = capsys.readouterr().err
    assert "Traceback" in err
    assert "ollama refused the connection" in err
