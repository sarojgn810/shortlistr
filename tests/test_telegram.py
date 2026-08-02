"""CH3 — Telegram inbound routing (chat core + Telegram HTTP mocked)."""

from __future__ import annotations

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))


def test_text_message_routes_to_chat_and_replies(monkeypatch):
    from connectors import telegram

    sent: list = []
    path = os.path.join(tempfile.mkdtemp(), "tg.json")
    monkeypatch.setattr(telegram, "_call", lambda method, token, **p: sent.append((method, p)) or {})
    monkeypatch.setattr(
        telegram,
        "chat",
        lambda msg, history=None, **k: {"reply": "hello there"},
    )
    monkeypatch.setattr(telegram, "_state_path", lambda: path)

    telegram.handle_update({"message": {"text": "hi", "chat": {"id": 7}}}, "tok")
    assert any(m == "sendMessage" and p.get("text") == "hello there" for m, p in sent)
    assert telegram.linked_chat_id() == 7


def test_submit_action_shows_confirm_buttons(monkeypatch):
    from connectors import telegram

    sent: list = []
    path = os.path.join(tempfile.mkdtemp(), "tg.json")
    monkeypatch.setattr(telegram, "_call", lambda method, token, **p: sent.append((method, p)) or {})
    monkeypatch.setattr(telegram, "chat", lambda msg, history=None, **k: {
        "reply": "needs confirm",
        "pending_confirm": {"tool": "channel.send", "args": {}, "prompt": "Run channel.send?"},
    })
    monkeypatch.setattr(telegram, "_state_path", lambda: path)
    telegram._PENDING.clear()

    telegram.handle_update({"message": {"text": "email them", "chat": {"id": 9}}}, "tok")
    assert telegram._PENDING.get(9, {}).get("tool") == "channel.send"
    assert any(m == "sendMessage" and p.get("reply_markup") for m, p in sent)


def test_callback_confirm_runs_gated_tool(monkeypatch):
    from connectors import telegram

    calls: dict = {}

    def fake_chat(msg, **k):
        if k.get("confirm_tool"):
            calls["confirmed"] = k["confirm_tool"]
            return {"reply": "done"}
        return {"reply": "x"}

    monkeypatch.setattr(telegram, "chat", fake_chat)
    monkeypatch.setattr(telegram, "_call", lambda *a, **k: {})
    telegram._PENDING[5] = {"tool": "channel.send", "args": {"to": "a@b.com"}, "prompt": "?"}

    telegram.handle_update(
        {"callback_query": {"id": "c1", "data": "confirm", "message": {"chat": {"id": 5}}}}, "tok"
    )
    assert calls.get("confirmed") == "channel.send"


def test_start_command_links_without_llm(monkeypatch):
    from connectors import telegram

    sent: list = []
    path = os.path.join(tempfile.mkdtemp(), "tg.json")
    monkeypatch.setattr(telegram, "_call", lambda method, token, **p: sent.append((method, p)) or {})
    monkeypatch.setattr(telegram, "_state_path", lambda: path)

    telegram.handle_update({"message": {"text": "/start", "chat": {"id": 42}}}, "tok")
    assert telegram.linked_chat_id() == 42
    assert any("Shortlistr agent" in (p.get("text") or "") for m, p in sent if m == "sendMessage")

