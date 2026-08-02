"""CH1 — conversational control core.

Turns a natural-language message into an answer and/or gated tool calls, shared by
the dashboard chat panel and the Telegram bot. Provider-agnostic: the LLM base only
offers complete(), so this runs a JSON tool-loop (the model emits one action per
turn). Submit-class tools are never auto-run — they surface a confirmation. With no
LLM configured, a tiny command parser keeps basic control working.
"""

from __future__ import annotations

import json
import logging
import re

from agent import dispatch, registry

logger = logging.getLogger(__name__)

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
    try:
        from agent.user_context import context_block

        identity = context_block()
    except Exception:
        identity = ""

    base = (
        "You are the user's job-search agent for Shortlistr. You know their profile "
        "and can take actions via tools — not just chat.\n"
        "Reply with EXACTLY ONE JSON object per turn, nothing else:\n"
        '  {"action":"answer","text":"..."}  — to reply to the user\n'
        '  {"action":"call_tool","tool":"<name>","args":{...}}  — to run a tool\n'
        "Use tools to fetch facts or change state before answering. For submit-class "
        "tools, still emit call_tool; the system will ask the user to confirm.\n"
        "Never invent employers, metrics, or skills that are not in the profile/CV "
        "or tool observations. Never claim you submitted an application.\n"
        "When action is answer, keep text concrete and direct.\n"
        f"{identity}\n\n"
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
            # Misconfigured model / outage must degrade to basic commands, not a
            # raw exception the user cannot act on.
            logger.warning("chat LLM failed (%s) — falling back to commands", e)
            fb = _fallback(message, tenant_id)
            if actions:
                fb = {**fb, "actions": actions + list(fb.get("actions") or [])}
            return fb
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
    cta = (
        "For full chat and stronger evaluations, open Connections and paste a free "
        "Groq API key (console.groq.com), or set up Local AI."
    )
    msg = (message or "").lower().strip()
    try:
        if "status" in msg or msg in ("how am i doing", "how's it going"):
            snap = dispatch.call_tool("shortlistr.status", {}, tenant_id=tenant_id)
            pipe = snap.get("pipeline") or snap.get("counts") or snap
            return {
                "reply": f"Status snapshot: {json.dumps(pipe)[:500]}\n\n{cta}",
                "actions": [{"tool": "shortlistr.status", "result": snap}],
                "needs_llm": True,
            }
        if "inbox" in msg or ("jobs" in msg and "prep" not in msg):
            jobs = dispatch.call_tool("shortlistr.list_jobs", {"status": "inbox"}, tenant_id=tenant_id)
            return {
                "reply": f"{len(jobs)} job(s) in your inbox. Open Discover to review them.\n\n{cta}",
                "actions": [{"tool": "shortlistr.list_jobs", "result": jobs}],
                "needs_llm": True,
            }
        if "discover" in msg or "scan" in msg:
            res = dispatch.call_tool("shortlistr.discover", {"dry_run": True}, tenant_id=tenant_id)
            return {
                "reply": (
                    f"Discovery dry-run found {res.get('discovered', 0)} matching role(s). "
                    f"Use Scan on Discover to run for real.\n\n{cta}"
                ),
                "actions": [{"tool": "shortlistr.discover", "result": res}],
                "needs_llm": True,
            }
        if "pipeline" in msg:
            jobs = dispatch.call_tool("shortlistr.list_jobs", {"status": "evaluated"}, tenant_id=tenant_id)
            return {
                "reply": f"{len(jobs)} evaluated job(s) in the pipeline. Open Pipeline in the sidebar.\n\n{cta}",
                "actions": [{"tool": "shortlistr.list_jobs", "result": jobs}],
                "needs_llm": True,
            }
        if "prep" in msg:
            tokens = msg.replace(",", " ").split()
            job_id = next((t for t in tokens if len(t) >= 8 and t.isalnum()), None)
            if job_id:
                res = dispatch.call_tool("shortlistr.prep", {"job_id": job_id}, tenant_id=tenant_id)
                return {
                    "reply": f"Prep ready for {job_id}: cover letter + guide generated.\n\n{cta}",
                    "actions": [{"tool": "shortlistr.prep", "result": res}],
                    "needs_llm": True,
                }
            return {
                "reply": f"Open Prep in the sidebar, or say: prep <job_id>\n\n{cta}",
                "actions": [],
                "needs_llm": True,
            }
        if msg in ("whoami", "who am i", "my profile", "profile") or "who am i" in msg:
            snap = dispatch.call_tool("shortlistr.whoami", {}, tenant_id=tenant_id)
            name = snap.get("name") or "not set"
            titles = ", ".join(snap.get("target_titles") or []) or "none"
            return {
                "reply": f"You're {name}. Targeting: {titles}.\n\n{cta}",
                "actions": [{"tool": "shortlistr.whoami", "result": snap}],
                "needs_llm": True,
            }
        if msg.startswith("approve ") or msg.startswith("skip "):
            parts = msg.split()
            job_id = parts[1] if len(parts) > 1 else ""
            tool = "shortlistr.queue_apply" if parts[0] == "approve" else "shortlistr.skip"
            if job_id:
                res = dispatch.call_tool(tool, {"job_id": job_id}, tenant_id=tenant_id)
                return {
                    "reply": f"{parts[0].title()}d {job_id}.\n\n{cta}",
                    "actions": [{"tool": tool, "result": res}],
                    "needs_llm": True,
                }
        if msg in ("help", "?", "hi", "hello", "hey") or not msg:
            return {
                "reply": (
                    "AI is not connected yet — I can still run basic commands: "
                    "status, inbox, discover, pipeline, whoami, approve <id>, skip <id>, prep <id>.\n\n"
                    + cta
                ),
                "actions": [],
                "needs_llm": True,
            }
    except Exception as e:
        return {
            "reply": f"Something went wrong: {e}\n\n{cta}",
            "actions": [],
            "needs_llm": True,
        }
    return {
        "reply": (
            "I only understand a few commands without AI: "
            "status, inbox, discover, pipeline, whoami, approve <id>, skip <id>, or prep <id>.\n\n"
            + cta
        ),
        "actions": [],
        "needs_llm": True,
    }
