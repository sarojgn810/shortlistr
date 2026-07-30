"""CH3 — Telegram inbound front-end onto the chat core (CH1).

Long-polls getUpdates (the laptop dials OUT — no inbound port/tunnel/exposure).
Each message routes through agent.chat.chat; submit-class actions surface inline
Confirm/Cancel buttons. Bot token lives in the keychain (TELEGRAM_BOT_TOKEN).

Run:  make telegram   (or: python3 -m automation.cli telegram)
"""

from __future__ import annotations

import logging
import time

import requests

from agent.chat import chat
from secrets_store import get_secret

logger = logging.getLogger(__name__)

_URL = "https://api.telegram.org/bot{token}/{method}"
_PENDING: dict[int, dict] = {}  # chat_id → pending_confirm


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
    _call("sendMessage", token, chat_id=chat_id, text=(text or "(no reply)")[:4000],
          reply_markup=markup)


def handle_update(update: dict, token: str) -> None:
    if update.get("message", {}).get("text"):
        msg = update["message"]
        chat_id = msg["chat"]["id"]
        res = chat(msg["text"], tenant_id="default")
        pending = res.get("pending_confirm")
        if pending:
            _PENDING[chat_id] = pending
            _send(token, chat_id, f"{res.get('reply', '')}\n\n{pending['prompt']}", with_confirm=True)
        else:
            _send(token, chat_id, res.get("reply", ""))
        return

    if "callback_query" in update:
        cq = update["callback_query"]
        chat_id = cq["message"]["chat"]["id"]
        _call("answerCallbackQuery", token, callback_query_id=cq["id"])
        pending = _PENDING.pop(chat_id, None)
        if cq.get("data") == "confirm" and pending:
            res = chat("", confirm_tool=pending["tool"], confirm_args=pending["args"])
            _send(token, chat_id, res.get("reply", "Done."))
        else:
            _send(token, chat_id, "Cancelled.")


def run_loop(*, once: bool = False, poll_timeout: int = 50) -> int:
    token = get_secret("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("No TELEGRAM_BOT_TOKEN in keychain — set it first (onboarding or keychain).")
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
