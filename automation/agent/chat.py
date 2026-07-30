"""CH1 — conversational control core.

Turns a natural-language message into an answer and/or gated tool calls, shared by
the dashboard chat panel and the Telegram bot. Provider-agnostic: the LLM base only
offers complete(), so this runs a JSON tool-loop (the model emits one action per
turn). Submit-class tools are never auto-run — they surface a confirmation. With no
LLM configured, a tiny command parser keeps basic control working.
"""

from __future__ import annotations

import json
import re

from agent import dispatch, registry

MAX_STEPS = 5


def _tool_catalog() -> str:
    lines = []
    for t in registry.list_tools():
        lines.append(f"- {t['name']} [{t['side_effect']}]: {t['description']}")
    return "\n".join(lines)


def _memory_block(tenant_id: str) -> str:
    try:
        from memory.store import search_learnings

        items = search_learnings("", limit=6, tenant_id=tenant_id)
        if items:
            return "\nKnown learnings:\n" + "\n".join(f"- {i['insight']}" for i in items)
    except Exception:
        pass
    return ""


def _system_prompt(tenant_id: str) -> str:
    base = (
        "You are shortlistr's assistant. You help the user run their job search and can call tools.\n"
        "Reply with EXACTLY ONE JSON object per turn, nothing else:\n"
        '  {"action":"answer","text":"..."}  — to reply to the user\n'
        '  {"action":"call_tool","tool":"<name>","args":{...}}  — to run a tool\n'
        "Use tools to fetch facts before answering. For submit-class tools, still emit "
        "call_tool; the system will ask the user to confirm before running them.\n"
        "When action is answer, keep text concrete and direct — no fluff or banned filler phrases.\n\n"
        f"Available tools:\n{_tool_catalog()}{_memory_block(tenant_id)}"
    )
    try:
        from writing.style import with_style

        return with_style(base)
    except Exception:
        return base


def _sanitize_reply(text: str) -> str:
    try:
        from writing.sanitize import sanitize

        return sanitize(text or "", mode="prose")
    except Exception:
        return text or ""


def _parse_action(raw: str) -> dict:
    m = re.search(r"\{[\s\S]*\}", raw or "")
    if m:
        try:
            obj = json.loads(m.group(0))
            if isinstance(obj, dict) and obj.get("action"):
                return obj
        except Exception:
            pass
    return {"action": "answer", "text": (raw or "").strip()[:1000]}


def _confirm_prompt(name: str, args: dict) -> str:
    return f"Run {name} with {json.dumps(args)}? Reply 'yes' to confirm."


def chat(
    message: str,
    history: list[dict] | None = None,
    *,
    tenant_id: str = "default",
    confirm_tool: str | None = None,
    confirm_args: dict | None = None,
) -> dict:
    """Returns {reply, actions, pending_confirm?}. confirm_tool runs a previously-gated submit."""
    if confirm_tool:
        try:
            result = dispatch.call_tool(confirm_tool, confirm_args or {}, confirm=True, tenant_id=tenant_id)
            return {"reply": f"Done: {confirm_tool}.", "actions": [{"tool": confirm_tool, "result": result}]}
        except Exception as e:
            return {"reply": f"Could not run {confirm_tool}: {e}", "actions": []}

    from llm import get_llm

    provider = get_llm()
    if not provider or not provider.is_available():
        return _fallback(message, tenant_id)

    system = _system_prompt(tenant_id)
    convo = ""
    for turn in history or []:
        convo += f"{turn.get('role', 'user').capitalize()}: {turn.get('content', '')}\n"
    convo += f"User: {message}\n"

    actions: list[dict] = []
    for _ in range(MAX_STEPS):
        try:
            raw = provider.complete(convo, system=system, max_tokens=800)
        except Exception as e:
            return {"reply": f"LLM error: {e}", "actions": actions}
        action = _parse_action(raw)

        if action["action"] == "answer":
            return {"reply": _sanitize_reply(action.get("text", "")), "actions": actions}

        if action["action"] == "call_tool":
            name = action.get("tool", "")
            args = action.get("args", {}) or {}
            tool = registry.get_tool(name)
            if tool is None:
                convo += f"\nObservation: unknown tool {name}\n"
                continue
            if tool.side_effect == registry.SUBMIT:
                return {
                    "reply": _sanitize_reply(
                        action.get("text") or "This needs your confirmation."
                    ),
                    "pending_confirm": {"tool": name, "args": args, "prompt": _confirm_prompt(name, args)},
                    "actions": actions,
                }
            try:
                result = dispatch.call_tool(name, args, confirm=False, tenant_id=tenant_id)
            except Exception as e:
                result = {"error": str(e)}
            actions.append({"tool": name, "result": result})
            convo += f"\nObservation from {name}: {json.dumps(result)[:1200]}\n"
            continue

        return {"reply": _sanitize_reply(action.get("text", raw[:500])), "actions": actions}

    return {"reply": "Stopped after several steps without a final answer.", "actions": actions}


def _fallback(message: str, tenant_id: str) -> dict:
    """No-LLM command parser so basic control still works without a key."""
    msg = (message or "").lower().strip()
    try:
        if "status" in msg or msg in ("how am i doing", "how's it going"):
            return {
                "reply": json.dumps(dispatch.call_tool("shortlistr.status", {}, tenant_id=tenant_id)),
                "actions": [{"tool": "shortlistr.status"}],
            }
        if "inbox" in msg or ("jobs" in msg and "prep" not in msg):
            jobs = dispatch.call_tool("shortlistr.list_jobs", {"status": "inbox"}, tenant_id=tenant_id)
            return {
                "reply": f"{len(jobs)} jobs in inbox.",
                "actions": [{"tool": "shortlistr.list_jobs", "result": jobs}],
            }
        if "discover" in msg or "scan" in msg:
            res = dispatch.call_tool("shortlistr.discover", {"dry_run": True}, tenant_id=tenant_id)
            return {
                "reply": f"Discovery (dry run): {res.get('discovered', 0)} found.",
                "actions": [{"tool": "shortlistr.discover"}],
            }
        if "pipeline" in msg:
            jobs = dispatch.call_tool("shortlistr.list_jobs", {"status": "evaluated"}, tenant_id=tenant_id)
            return {
                "reply": f"{len(jobs)} evaluated job(s) in the pipeline. Open Pipeline in the sidebar for the board.",
                "actions": [{"tool": "shortlistr.list_jobs", "result": jobs}],
            }
        if "prep" in msg:
            return {
                "reply": "Open Prep in the sidebar to review cover letters and interview guides for approved roles.",
                "actions": [],
            }
    except Exception as e:
        return {"reply": f"Error: {e}", "actions": []}
    return {
        "reply": (
            "AI helper is not set up, so I can only run a few commands: "
            "status, inbox, discover, pipeline, or prep.\n\n"
            "For full chat, open Connections and add an AI provider + key."
        ),
        "actions": [],
    }
