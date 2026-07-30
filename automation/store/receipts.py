"""Application receipts — immutable submit records (J1.3)."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from store import db as store
from store.status import validate_job_id

MAX_FIELDS_BYTES = 65_536
MAX_COVER_LETTER_BYTES = 32_768
MAX_PATH_LEN = 512

_ALLOWED_CHANNELS = frozenset({"email", "prep", "manual", "ats_assist"})
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ReceiptError(ValueError):
    pass


def _sanitize_path(path: str | None) -> str | None:
    if not path:
        return None
    p = path.strip()
    if len(p) > MAX_PATH_LEN:
        raise ReceiptError("resume_path too long")
    if ".." in p or p.startswith("/etc") or p.startswith("/var"):
        raise ReceiptError("invalid resume_path")
    return p


def _sanitize_fields(fields: dict[str, Any] | None) -> str:
    data = fields or {}
    if not isinstance(data, dict):
        raise ReceiptError("fields must be a dict")
    # Strip keys that look like secrets
    clean: dict[str, Any] = {}
    for k, v in data.items():
        key = str(k)[:128]
        if any(x in key.lower() for x in ("password", "token", "secret", "api_key")):
            continue
        if isinstance(v, str):
            clean[key] = v[:4000]
        elif isinstance(v, (int, float, bool)) or v is None:
            clean[key] = v
        else:
            clean[key] = str(v)[:4000]
    raw = json.dumps(clean, ensure_ascii=False)
    if len(raw.encode("utf-8")) > MAX_FIELDS_BYTES:
        raise ReceiptError("fields_json exceeds size limit")
    return raw


def _sanitize_cover_letter(text: str | None) -> str | None:
    if not text:
        return None
    t = text.strip()
    if len(t.encode("utf-8")) > MAX_COVER_LETTER_BYTES:
        raise ReceiptError("cover_letter_text exceeds size limit")
    return t


def create_receipt(
    job_id: str,
    channel: str,
    *,
    fields: dict[str, Any] | None = None,
    resume_path: str | None = None,
    cover_letter_text: str | None = None,
    application_id: int | None = None,
    actor: str = "system",
) -> int:
    """Persist an application receipt and audit entry."""
    jid = validate_job_id(job_id)
    ch = channel.strip().lower()
    if ch not in _ALLOWED_CHANNELS:
        raise ReceiptError(f"Invalid channel: {channel}")

    fields_json = _sanitize_fields(fields)
    resume = _sanitize_path(resume_path)
    cover = _sanitize_cover_letter(cover_letter_text)
    submitted_at = datetime.now(timezone.utc).isoformat()

    # Validate email in fields if present
    if fields:
        to_email = fields.get("to_email") or fields.get("to")
        if to_email and isinstance(to_email, str) and not _EMAIL_RE.match(to_email):
            raise ReceiptError("invalid to_email in fields")

    with store.db() as conn:
        job = conn.execute("SELECT id FROM jobs WHERE id = ?", (jid,)).fetchone()
        if not job:
            raise ReceiptError(f"Job {jid} not found")

        cur = conn.execute(
            """
            INSERT INTO application_receipts (
                application_id, job_id, channel, fields_json,
                resume_path, cover_letter_text, submitted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (application_id, jid, ch, fields_json, resume, cover, submitted_at),
        )
        receipt_id = int(cur.lastrowid)

    store.audit(
        "application_receipt",
        "receipt",
        str(receipt_id),
        {
            "job_id": jid,
            "channel": ch,
            "application_id": application_id,
            "actor": actor,
        },
    )
    return receipt_id


def list_receipts_for_job(job_id: str, *, limit: int = 20) -> list[dict]:
    jid = validate_job_id(job_id)
    limit = max(1, min(limit, 100))
    with store.db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM application_receipts
            WHERE job_id = ? ORDER BY submitted_at DESC LIMIT ?
            """,
            (jid, limit),
        ).fetchall()
    out = []
    for row in rows:
        d = dict(row)
        try:
            d["fields"] = json.loads(d.pop("fields_json", "{}") or "{}")
        except json.JSONDecodeError:
            d["fields"] = {}
        out.append(d)
    return out


def get_receipt(receipt_id: int) -> dict | None:
    if receipt_id < 1:
        raise ReceiptError("invalid receipt_id")
    with store.db() as conn:
        row = conn.execute(
            "SELECT * FROM application_receipts WHERE id = ?", (receipt_id,)
        ).fetchone()
    if not row:
        return None
    d = dict(row)
    try:
        d["fields"] = json.loads(d.pop("fields_json", "{}") or "{}")
    except json.JSONDecodeError:
        d["fields"] = {}
    return d
