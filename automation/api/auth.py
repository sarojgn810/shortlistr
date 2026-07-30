"""Simple JWT auth helpers for Phase 2 multi-tenant API."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Optional

# No shipped default. "dev-change-me" was a signing key published in the source
# of a public repo: anyone who read it could mint a valid owner token for any
# instance that had not overridden it. An unset secret now becomes a random
# per-process value, so tokens stop working across a restart — survivable, in a
# way that a predictable signing key is not.
_FALLBACK = secrets.token_urlsafe(32)
SECRET = os.environ.get("SHORTLISTR_JWT_SECRET", "").strip() or _FALLBACK


def secret_is_ephemeral() -> bool:
    """True when SHORTLISTR_JWT_SECRET is unset, so tokens will not survive a
    restart. Callers that bind a public port should refuse."""
    return SECRET is _FALLBACK


def create_token(sub: str, tenant_id: str = "default", role: str = "owner", ttl: int = 86400) -> str:
    payload = {
        "sub": sub,
        "tenant_id": tenant_id,
        "role": role,
        "exp": int(time.time()) + ttl,
    }
    body = json.dumps(payload, separators=(",", ":")).encode()
    sig = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    import base64
    return base64.urlsafe_b64encode(body).decode().rstrip("=") + "." + sig


def verify_token(token: str) -> Optional[dict]:
    try:
        import base64
        body_b64, sig = token.split(".", 1)
        pad = "=" * (-len(body_b64) % 4)
        body = base64.urlsafe_b64decode(body_b64 + pad)
        expected = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig):
            return None
        payload = json.loads(body)
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None
