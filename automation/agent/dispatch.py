"""Unified tool dispatch: one path that gates then routes (built-in | MCP).

Every agent-initiated tool call goes through here so the F2 permission gate is
enforced uniformly, whether the tool is built-in (e.g. channel.send) or imported
from an MCP server (mcp.<server>.<tool>).
"""

from __future__ import annotations

from typing import Any

from agent.registry import check_permission


def _channel_send(args: dict) -> dict:
    from channels.registry import get_channel

    ch = get_channel(args.get("channel"))
    res = ch.send(
        args["to"],
        args.get("subject", ""),
        args.get("body", ""),
        attachments=args.get("attachments"),
        dry_run=bool(args.get("dry_run", False)),
    )
    return {"ok": res.ok, "detail": res.detail}


def _status(args: dict) -> dict:
    from store import db
    from store.status import application_status_counts

    db.init_db()
    return {"applications": application_status_counts(), "pipeline": db.pipeline_breakdown()}


def _list_jobs(args: dict) -> list[dict]:
    from store import db

    db.init_db()
    status = args.get("status", "inbox")
    pipe = "pending" if status == "inbox" else status
    with db.db() as conn:
        rows = conn.execute(
            "SELECT j.id, j.company, j.title FROM jobs j JOIN pipeline p ON p.job_id = j.id "
            "WHERE p.status = ? ORDER BY p.added_at DESC LIMIT 25",
            (pipe,),
        ).fetchall()
    return [dict(r) for r in rows]


def _discover(args: dict) -> dict:
    from scheduler.scan_scheduler import run_scheduled_scan

    return run_scheduled_scan(dry_run=bool(args.get("dry_run", False)))


def _evaluate(args: dict) -> dict:
    from api.jobs_api import prepare_job_for_eval
    from eval.service import evaluate_job_text
    from store import db

    db.init_db()
    with db.db() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (args["job_id"],)).fetchone()
    if not row:
        return {"error": "job not found"}
    jd, company, role, url = prepare_job_for_eval(dict(row))
    r = evaluate_job_text(jd, url=url, company=company or "", role=role or "")
    out = {"score": r.score, "legitimacy": r.legitimacy, "eval_mode": r.eval_mode}
    # Phone ping for strong matches when Telegram is linked + bot is running.
    try:
        if r.score is not None and float(r.score) >= 3.5:
            from connectors.telegram import notify_job

            notify_job(
                {
                    "id": args["job_id"],
                    "company": company,
                    "title": role,
                    "score": r.score,
                    "url": url,
                }
            )
    except Exception:
        pass
    return out


def _explain(args: dict) -> dict:
    from eval.explain import explain_job

    return explain_job(args["job_id"])


def _queue_apply(args: dict) -> dict:
    from store.status import mark_approved

    return mark_approved(args["job_id"], actor="chat")


def _skip(args: dict) -> dict:
    from store.status import mark_skipped

    return mark_skipped(args["job_id"], actor="chat")


def _whoami(args: dict) -> dict:
    from agent.user_context import profile_snapshot

    return profile_snapshot()


def _prep(args: dict) -> dict:
    from api.prep_bundle import generate_prep_bundle

    bundle = generate_prep_bundle(args["job_id"])
    return {
        "job_id": bundle.get("job_id"),
        "company": bundle.get("company"),
        "role": bundle.get("role"),
        "url": bundle.get("url"),
        "apply_channel": bundle.get("apply_channel"),
        "has_cover": bool((bundle.get("cover_letter") or {}).get("body")),
        "has_prep_guide": bool(bundle.get("prep_content") or bundle.get("prep_path")),
        "cv_pdf_path": bundle.get("cv_pdf_path"),
    }


def _apply_assist(args: dict) -> dict:
    from apply.ats_fill import apply_assist_for_job

    return apply_assist_for_job(args["job_id"], headless=bool(args.get("headless", True)))


def _resolve_jobs(args: dict) -> dict:
    from store import db
    from store.enrich import backfill_all_jobs

    db.init_db()
    with db.db() as conn:
        n = backfill_all_jobs(conn, max_jobs=int(args.get("limit", 50)))
    return {"resolved": n}


_BUILTIN_HANDLERS = {
    "channel.send": _channel_send,
    "shortlistr.status": _status,
    "shortlistr.list_jobs": _list_jobs,
    "shortlistr.discover": _discover,
    "shortlistr.evaluate": _evaluate,
    "shortlistr.explain": _explain,
    "shortlistr.queue_apply": _queue_apply,
    "shortlistr.skip": _skip,
    "shortlistr.whoami": _whoami,
    "shortlistr.prep": _prep,
    "shortlistr.apply_assist": _apply_assist,
    "shortlistr.resolve_jobs": _resolve_jobs,
}


def _call_mcp(name: str, args: dict) -> Any:
    _, server_name, tool = name.split(".", 2)
    from config import MCP_SERVERS
    from connectors import client

    server = next((s for s in MCP_SERVERS if s.get("name") == server_name), None)
    if not server:
        raise ValueError(f"MCP server not configured: {server_name}")
    return client.call_tool(server, tool, args)


def call_tool(name: str, args: dict | None = None, *, confirm: bool = False, tenant_id: str = "default") -> Any:
    """Gate, then route. Raises PermissionDenied (gate) or ValueError (unknown tool)."""
    args = args or {}
    check_permission(name, confirm=confirm, tenant_id=tenant_id)
    if name.startswith("mcp."):
        return _call_mcp(name, args)
    handler = _BUILTIN_HANDLERS.get(name)
    if handler is None:
        raise ValueError(f"Unknown or non-dispatchable tool: {name}")
    return handler(args)
