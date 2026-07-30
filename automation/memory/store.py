"""Agent memory API over SQLite.

Tiers:
  - semantic / long-term : `learnings` table (this module's add/search)
  - episodic             : the existing `audit_log` (recent_events) — no dup table
  - working              : a JSON blob via store.settings (get/set_working_memory)

search_learnings is keyword-based today; the signature is the seam for a local
embedding backend under the deferred bundled-LLM pillar.
"""

from __future__ import annotations

import json
from typing import Any

from store import db as _db


def add_learning(
    insight: str,
    *,
    kind: str = "insight",
    key: str | None = None,
    confidence: int = 5,
    source: str = "observed",
    refs: list | None = None,
    tenant_id: str = "default",
) -> int:
    _db.init_db()
    with _db.db() as conn:
        cur = conn.execute(
            "INSERT INTO learnings (tenant_id, kind, key, insight, confidence, source, refs) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (tenant_id, kind, key, insight, int(confidence), source, json.dumps(refs or [])),
        )
        conn.commit()
        return int(cur.lastrowid)


def clear_learnings(kind: str, tenant_id: str = "default") -> int:
    """Delete all learnings of a kind for a tenant (idempotent recompute support)."""
    _db.init_db()
    with _db.db() as conn:
        cur = conn.execute(
            "DELETE FROM learnings WHERE tenant_id = ? AND kind = ?", (tenant_id, kind)
        )
        conn.commit()
        return cur.rowcount


def _row_to_dict(row) -> dict[str, Any]:
    d = dict(row)
    try:
        d["refs"] = json.loads(d.get("refs") or "[]")
    except Exception:
        d["refs"] = []
    return d


def search_learnings(query: str = "", *, limit: int = 10, tenant_id: str = "default") -> list[dict]:
    _db.init_db()
    terms = [t for t in (query or "").lower().split() if t]
    with _db.db() as conn:
        if not terms:
            rows = conn.execute(
                "SELECT * FROM learnings WHERE tenant_id = ? ORDER BY id DESC LIMIT ?",
                (tenant_id, limit),
            ).fetchall()
        else:
            clause = " OR ".join(
                "(LOWER(insight) LIKE ? OR LOWER(IFNULL(key,'')) LIKE ?)" for _ in terms
            )
            params: list[Any] = [tenant_id]
            for t in terms:
                like = f"%{t}%"
                params.extend([like, like])
            params.append(limit)
            rows = conn.execute(
                f"SELECT * FROM learnings WHERE tenant_id = ? AND ({clause}) "
                f"ORDER BY confidence DESC, id DESC LIMIT ?",
                params,
            ).fetchall()
    return [_row_to_dict(r) for r in rows]


def recent_events(limit: int = 20, tenant_id: str = "default") -> list[dict]:
    """Episodic memory — reads the existing audit_log."""
    _db.init_db()
    with _db.db() as conn:
        rows = conn.execute(
            "SELECT action, resource_type, resource_id, details_json, created_at "
            "FROM audit_log WHERE tenant_id = ? ORDER BY id DESC LIMIT ?",
            (tenant_id, limit),
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["details"] = json.loads(d.pop("details_json") or "{}")
        except Exception:
            d["details"] = {}
        out.append(d)
    return out


def get_working_memory(tenant_id: str = "default") -> dict:
    from store.settings import _get_json

    return _get_json(tenant_id, "working_memory", {})


def set_working_memory(data: dict, tenant_id: str = "default") -> dict:
    from store.settings import _set_json

    return _set_json(tenant_id, "working_memory", data)
