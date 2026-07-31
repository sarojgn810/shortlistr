"""Telegram front-end onto the chat agent (same core as the dashboard dock).

Long-polls getUpdates (laptop dials OUT — no inbound port). Each message routes
through agent.chat.chat with the user's profile context and short history.
Submit-class actions get Confirm/Cancel buttons.

Outbound: call notify(text) once the user has messaged the bot once (chat_id saved).

Run:  make telegram   (or: python3 -m automation.cli telegram)
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

import requests

from agent.chat import chat
from secrets_store import get_secret

logger = logging.getLogger(__name__)

_URL = "https://api.telegram.org/bot{token}/{method}"
_PENDING: dict[int, dict] = {}  # chat_id → pending_confirm
_HISTORY_LIMIT = 8  # turns kept per chat (user+assistant pairs count as 2)


def _state_path() -> str:
    try:
        import config

        return os.path.join(config.DATA_DIR, "telegram_bot.json")
    except Exception:
        return os.path.join("data", "telegram_bot.json")


def _load_state() -> dict[str, Any]:
    path = _state_path()
    if not os.path.isfile(path):
        return {"chat_id": None, "history": {}}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"chat_id": None, "history": {}}
        data.setdefault("chat_id", None)
        data.setdefault("history", {})
        return data
    except Exception:
        return {"chat_id": None, "history": {}}


def _save_state(state: dict[str, Any]) -> None:
    path = _state_path()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, path)


def linked_chat_id() -> int | None:
    raw = _load_state().get("chat_id")
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def remember_chat(chat_id: int) -> None:
    state = _load_state()
    state["chat_id"] = int(chat_id)
    _save_state(state)


def _history_for(chat_id: int) -> list[dict]:
    state = _load_state()
    hist = state.get("history") or {}
    raw = hist.get(str(chat_id)) or []
    return [h for h in raw if isinstance(h, dict)][-_HISTORY_LIMIT:]


def _append_history(chat_id: int, role: str, content: str) -> None:
    state = _load_state()
    hist = state.setdefault("history", {})
    key = str(chat_id)
    turns = list(hist.get(key) or [])
    turns.append({"role": role, "content": (content or "")[:2000]})
    hist[key] = turns[-_HISTORY_LIMIT:]
    state["chat_id"] = int(chat_id)
    _save_state(state)


def _call(method: str, token: str, **params) -> dict:
    resp = requests.post(_URL.format(token=token, method=method), json=params, timeout=70)
    return resp.json()


def _send(token: str, chat_id: int, text: str, *, with_confirm: bool = False) -> None:
    markup = None
    if with_confirm:
        markup = {"inline_keyboard": [[
            {"text": "✅ Confirm", "callback_data": "confirm"},
            {"text": "✖ Cancel", "callback_data": "cancel"},
        ]]}
    _call(
        "sendMessage",
        token,
        chat_id=chat_id,
        text=(text or "(no reply)")[:4000],
        reply_markup=markup,
    )


def notify(text: str, *, with_confirm: bool = False) -> bool:
    """Push a message to the linked Telegram chat (after the user has messaged once)."""
    token = get_secret("TELEGRAM_BOT_TOKEN")
    chat_id = linked_chat_id()
    if not token or not chat_id:
        return False
    try:
        _send(token, chat_id, text, with_confirm=with_confirm)
        return True
    except Exception as e:
        logger.warning("Telegram notify failed: %s", e)
        return False


def notify_job(job: dict, *, prompt: str = "Reply approve <id> or skip <id>") -> bool:
    """Short job card for phone review."""
    jid = job.get("id") or job.get("job_id") or ""
    company = job.get("company") or "?"
    title = job.get("title") or "?"
    score = job.get("eval_score") or job.get("score")
    score_bit = f" · {score}/5" if score is not None else ""
    lines = [
        f"{company} — {title}{score_bit}",
        f"id: {jid}",
    ]
    if job.get("url"):
        lines.append(str(job["url"]))
    lines.append(prompt)
    return notify("\n".join(lines))


def handle_update(update: dict, token: str) -> None:
    if update.get("message", {}).get("text"):
        msg = update["message"]
        chat_id = int(msg["chat"]["id"])
        text = (msg.get("text") or "").strip()
        remember_chat(chat_id)

        if text.lower() in ("/start", "start", "/help", "help"):
            _send(
                token,
                chat_id,
                "Shortlistr agent on Telegram.\n"
                "I know your profile and can act: status, inbox, discover, "
                "evaluate, approve <id>, skip <id>, prep <id>, whoami.\n"
                "Risky actions (email / form prefill) ask for Confirm first.\n"
                "This chat stays linked for phone alerts after you message once.",
            )
            return

        history = _history_for(chat_id)
        res = chat(text, history=history, tenant_id="default")
        _append_history(chat_id, "user", text)
        reply = res.get("reply", "") or ""
        pending = res.get("pending_confirm")
        if pending:
            _PENDING[chat_id] = pending
            out = f"{reply}\n\n{pending['prompt']}".strip()
            _append_history(chat_id, "assistant", out)
            _send(token, chat_id, out, with_confirm=True)
        else:
            _append_history(chat_id, "assistant", reply)
            _send(token, chat_id, reply)

        # Surface tool side-effects briefly when the model answered without saying.
        actions = res.get("actions") or []
        if actions and not pending:
            tools = ", ".join(a.get("tool", "?") for a in actions if a.get("tool"))
            if tools and tools not in reply:
                logger.info("Telegram actions: %s", tools)
        return

    if "callback_query" in update:
        cq = update["callback_query"]
        chat_id = int(cq["message"]["chat"]["id"])
        _call("answerCallbackQuery", token, callback_query_id=cq["id"])
        pending = _PENDING.pop(chat_id, None)
        if cq.get("data") == "confirm" and pending:
            res = chat("", confirm_tool=pending["tool"], confirm_args=pending["args"])
            reply = res.get("reply", "Done.")
            _append_history(chat_id, "assistant", reply)
            _send(token, chat_id, reply)
        else:
            _send(token, chat_id, "Cancelled.")


def run_loop(*, once: bool = False, poll_timeout: int = 50) -> int:
    token = get_secret("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("No TELEGRAM_BOT_TOKEN in keychain — set it on Connections → Telegram.")
        return 1
    logger.info("Telegram bot polling (dial-out long-poll)…")
    offset = None
    while True:
        try:
            resp = _call("getUpdates", token, offset=offset, timeout=poll_timeout)
            for upd in resp.get("result", []):
                offset = upd["update_id"] + 1
                try:
                    handle_update(upd, token)
                except Exception as e:
                    logger.warning("update failed: %s", e)
        except Exception as e:
            logger.warning("poll error: %s", e)
            time.sleep(3)
        if once:
            break
    return 0


def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(description="shortlistr Telegram bot")
    p.add_argument("--once", action="store_true", help="poll a single batch then exit")
    args = p.parse_args(argv)
    return run_loop(once=args.once)
