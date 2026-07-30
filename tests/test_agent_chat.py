"""CH1 — conversational control core (LLM mocked; no network)."""

from __future__ import annotations

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))


def _isolate(monkeypatch):
    tmp = tempfile.mkdtemp()
    import config
    import store.db as db_mod

    monkeypatch.setattr(config, "DATA_DIR", tmp)
    monkeypatch.setattr(db_mod, "DATA_DIR", tmp)
    monkeypatch.setattr(db_mod, "DB_PATH", os.path.join(tmp, "shortlistr.db"))
    return tmp


class _FakeLLM:
    def __init__(self, responses):
        self._r = list(responses)
        self.i = 0

    def is_available(self):
        return True

    def complete(self, prompt, system="", max_tokens=1024):
        r = self._r[min(self.i, len(self._r) - 1)]
        self.i += 1
        return r


def test_chat_llm_tool_loop_then_answer(monkeypatch):
    _isolate(monkeypatch)
    import llm
    from store import db

    db.init_db()
    monkeypatch.setattr(llm, "get_llm", lambda: _FakeLLM([
        '{"action":"call_tool","tool":"shortlistr.status","args":{}}',
        '{"action":"answer","text":"Here is your status."}',
    ]))
    from agent.chat import chat

    out = chat("how is my search going?")
    assert out["reply"] == "Here is your status."
    assert any(a["tool"] == "shortlistr.status" for a in out["actions"])


def test_chat_submit_tool_needs_confirm(monkeypatch):
    _isolate(monkeypatch)
    import llm
    from store import db

    db.init_db()
    monkeypatch.setattr(llm, "get_llm", lambda: _FakeLLM([
        '{"action":"call_tool","tool":"channel.send","args":{"to":"a@b.com","subject":"h","body":"b"}}',
    ]))
    from agent.chat import chat

    out = chat("email the recruiter")
    assert "pending_confirm" in out
    assert out["pending_confirm"]["tool"] == "channel.send"
    assert out["actions"] == []  # not executed


def test_chat_confirm_runs_gated_tool(monkeypatch):
    _isolate(monkeypatch)
    from store import db

    db.init_db()
    from agent.chat import chat

    out = chat("", confirm_tool="channel.send",
               confirm_args={"to": "a@b.com", "subject": "h", "body": "b", "dry_run": True})
    assert "Done" in out["reply"]
    assert out["actions"][0]["tool"] == "channel.send"


def test_chat_fallback_without_llm(monkeypatch):
    _isolate(monkeypatch)
    import llm
    from store import db

    db.init_db()
    monkeypatch.setattr(llm, "get_llm", lambda: None)
    from agent.chat import chat

    out = chat("status")
    assert out["actions"] and out["actions"][0]["tool"] == "shortlistr.status"
