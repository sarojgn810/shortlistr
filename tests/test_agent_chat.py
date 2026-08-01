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
    assert out.get("needs_llm") is True
    assert "Groq" in out["reply"] or "Connections" in out["reply"]
    # Human summary — not a raw JSON dump of the whole status blob
    assert not out["reply"].strip().startswith("{")


def test_chat_fallback_help_cta(monkeypatch):
    _isolate(monkeypatch)
    import llm
    from store import db

    db.init_db()
    monkeypatch.setattr(llm, "get_llm", lambda: None)
    from agent.chat import chat

    out = chat("hello")
    assert out.get("needs_llm") is True
    assert "Groq" in out["reply"] or "console.groq.com" in out["reply"].lower()


def test_system_prompt_includes_profile(monkeypatch):
    _isolate(monkeypatch)
    import config
    from agent.chat import _system_prompt

    monkeypatch.setattr(
        config,
        "CANDIDATE",
        {
            "name": "Ada Example",
            "email": "ada@example.com",
            "years_exp": "8",
            "location": "Remote",
            "linkedin": "",
            "github": "",
            "phone": "",
        },
        raising=False,
    )
    monkeypatch.setattr(config, "_FILTERS", {"target_titles": ["SRE", "Platform"]}, raising=False)
    monkeypatch.setattr(config, "LOCATION_KEYWORDS", ["remote"], raising=False)
    monkeypatch.setattr(config, "_preferred_locations", lambda: ["Remote"], raising=False)

    prompt = _system_prompt("default")
    assert "Ada Example" in prompt
    assert "SRE" in prompt
    assert "shortlistr.whoami" in prompt
    assert "shortlistr.skip" in prompt


def test_whoami_and_skip_tools(monkeypatch):
    _isolate(monkeypatch)
    import config
    from models.job import JobRecord, job_id_from_url
    from store import db
    from store.status import mark_approved
    from agent import dispatch

    db.init_db()
    monkeypatch.setattr(
        config,
        "CANDIDATE",
        {"name": "Ada", "email": "a@b.com", "years_exp": "5", "location": "", "linkedin": "", "github": "", "phone": ""},
        raising=False,
    )
    monkeypatch.setattr(config, "_FILTERS", {"target_titles": ["SRE"]}, raising=False)
    monkeypatch.setattr(config, "LOCATION_KEYWORDS", [], raising=False)
    monkeypatch.setattr(config, "_preferred_locations", lambda: [], raising=False)

    snap = dispatch.call_tool("shortlistr.whoami", {})
    assert snap["name"] == "Ada"

    url = "https://boards.greenhouse.io/acme/jobs/skip-me"
    jid = job_id_from_url(url)
    db.upsert_job(JobRecord(url=url, source="test", company="Acme", title="SRE", job_id=jid))
    db.add_to_pipeline(jid, "evaluated")
    mark_approved(jid, actor="test")
    out = dispatch.call_tool("shortlistr.skip", {"job_id": jid})
    assert out["pipeline_status"] == "skipped"


def test_fallback_whoami(monkeypatch):
    _isolate(monkeypatch)
    import config
    import llm
    from store import db
    from agent.chat import chat

    db.init_db()
    monkeypatch.setattr(llm, "get_llm", lambda: None)
    monkeypatch.setattr(
        config,
        "CANDIDATE",
        {"name": "Ada", "email": "", "years_exp": "", "location": "", "linkedin": "", "github": "", "phone": ""},
        raising=False,
    )
    monkeypatch.setattr(config, "_FILTERS", {"target_titles": ["SRE"]}, raising=False)
    monkeypatch.setattr(config, "LOCATION_KEYWORDS", [], raising=False)
    monkeypatch.setattr(config, "_preferred_locations", lambda: [], raising=False)

    out = chat("whoami")
    assert "Ada" in out["reply"]
    assert out["actions"][0]["tool"] == "shortlistr.whoami"
