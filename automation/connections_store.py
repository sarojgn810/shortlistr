"""Read/write connector credentials for the Connections dashboard page.

Secrets (passwords, tokens) go through ``secrets_store`` — never into
``profile.yml``. Non-secret fields (platform emails, MCP server list) live in
the profile and are patched in place so a Connections save does not rewrite the
rest of the file.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from typing import Any

from config import SHORTLISTR_ROOT, BASE_DIR
from paths import PROFILE_PATH

logger = logging.getLogger(__name__)

# Canonical secret names the Connections UI owns. Aliases are checked on read so
# an older .env that used LINKEDIN_PASSWORD still shows as "set".
_SECRET_ALIASES: dict[str, tuple[str, ...]] = {
    "SHORTLISTR_LINKEDIN_PASSWORD": ("SHORTLISTR_LINKEDIN_PASSWORD", "LINKEDIN_PASSWORD"),
    "SHORTLISTR_NAUKRI_PASSWORD": ("SHORTLISTR_NAUKRI_PASSWORD", "NAUKRI_PASSWORD"),
    "GMAIL_APP_PASSWORD": ("GMAIL_APP_PASSWORD", "SHORTLISTR_EMAIL_PASSWORD"),
    "TELEGRAM_BOT_TOKEN": ("TELEGRAM_BOT_TOKEN",),
    "APIFY_TOKEN": ("APIFY_TOKEN",),
}

_WRITABLE_SECRETS = frozenset(_SECRET_ALIASES)


def _load_yaml() -> dict[str, Any]:
    import yaml

    if not os.path.isfile(PROFILE_PATH):
        return {}
    with open(PROFILE_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data if isinstance(data, dict) else {}


def _dump_yaml(data: dict[str, Any]) -> None:
    import yaml

    os.makedirs(os.path.dirname(PROFILE_PATH) or ".", exist_ok=True)
    with open(PROFILE_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def _secret_set(canonical: str) -> bool:
    from secrets_store import has_secret

    for name in _SECRET_ALIASES[canonical]:
        if has_secret(name):
            return True
    return False


def _write_secret(canonical: str, value: str | None) -> None:
    """Persist or clear a secret. ``None`` means leave unchanged; ``""`` clears."""
    if value is None:
        return
    from secrets_store import delete_secret, set_secret

    names = _SECRET_ALIASES[canonical]
    primary = names[0]
    if value.strip():
        set_secret(primary, value.strip())
        # Drop aliases so reads don't keep finding a stale copy.
        for alias in names[1:]:
            delete_secret(alias)
    else:
        for name in names:
            delete_secret(name)


def _gmail_oauth_status() -> dict[str, bool]:
    try:
        from config import GMAIL_CREDS_PATH, GMAIL_TOKEN_PATH

        creds = GMAIL_CREDS_PATH
        token = GMAIL_TOKEN_PATH
    except Exception:
        creds = os.path.join(BASE_DIR, "gmail_credentials.json")
        token = os.path.join(BASE_DIR, "gmail_token.pickle")
    return {
        "credentials_present": os.path.isfile(creds),
        "token_present": os.path.isfile(token),
    }


def _gmail_paths() -> tuple[str, str]:
    try:
        from config import GMAIL_CREDS_PATH, GMAIL_TOKEN_PATH

        return GMAIL_CREDS_PATH, GMAIL_TOKEN_PATH
    except Exception:
        return (
            os.path.join(BASE_DIR, "gmail_credentials.json"),
            os.path.join(BASE_DIR, "gmail_token.pickle"),
        )


def _playwright_status() -> dict[str, Any]:
    try:
        from doctor import check_playwright

        result = check_playwright()
        return {"installed": bool(result.get("pass")), "label": result.get("label", "")}
    except Exception as e:
        return {"installed": False, "label": str(e)}


def _local_ai_status() -> dict[str, Any]:
    try:
        from llm.local_ai import local_ai_status

        return local_ai_status()
    except Exception as e:
        return {
            "phase": "error",
            "ready": False,
            "message": str(e)[:200],
            "error": str(e)[:200],
            "model": "qwen2.5:0.5b",
        }


def _apify_status(data: dict[str, Any] | None = None) -> dict[str, Any]:
    """Whether Apify is enabled in profile + whether a token is saved."""
    data = data if data is not None else _load_yaml()
    sources = data.get("sources") if isinstance(data.get("sources"), dict) else {}
    enabled = sources.get("enabled") if isinstance(sources.get("enabled"), list) else []
    enabled_norm = [str(x).strip().lower() for x in enabled]
    token_set = _secret_set("APIFY_TOKEN")
    return {
        "token_set": token_set,
        "enabled": "apify" in enabled_norm,
        "ready": token_set and "apify" in enabled_norm,
    }


def get_connections_for_ui() -> dict[str, Any]:
    """Safe payload — flags and non-secret values only, never password contents."""
    data = _load_yaml()
    platforms = data.get("platforms") if isinstance(data.get("platforms"), dict) else {}
    linkedin = platforms.get("linkedin") if isinstance(platforms.get("linkedin"), dict) else {}
    naukri = platforms.get("naukri") if isinstance(platforms.get("naukri"), dict) else {}
    mcp = data.get("mcp_servers")
    if not isinstance(mcp, list):
        mcp = []

    candidate = data.get("candidate") if isinstance(data.get("candidate"), dict) else {}
    default_email = str(candidate.get("email") or "").strip()
    email_cfg = data.get("email") if isinstance(data.get("email"), dict) else {}
    sender = str(email_cfg.get("sender") or default_email or "").strip()

    return {
        "playwright": _playwright_status(),
        "local_ai": _local_ai_status(),
        "linkedin": {
            "email": str(linkedin.get("email") or default_email or "").strip(),
            "password_set": _secret_set("SHORTLISTR_LINKEDIN_PASSWORD"),
        },
        "naukri": {
            "email": str(naukri.get("email") or "").strip(),
            "password_set": _secret_set("SHORTLISTR_NAUKRI_PASSWORD"),
        },
        "gmail": {
            **_gmail_oauth_status(),
            "sender": sender,
            "app_password_set": _secret_set("GMAIL_APP_PASSWORD"),
        },
        "telegram": {
            "token_set": _secret_set("TELEGRAM_BOT_TOKEN"),
        },
        "apify": _apify_status(data),
        "mcp_servers": [
            {
                "name": str(s.get("name") or ""),
                "type": str(s.get("type") or s.get("transport") or "stdio"),
                "command": str(s.get("command") or ""),
                "args": list(s.get("args") or []) if isinstance(s.get("args"), list) else [],
                "url": str(s.get("url") or ""),
                "secret_ref": str(s.get("secret_ref") or ""),
            }
            for s in mcp
            if isinstance(s, dict)
        ],
    }


def save_connections_from_ui(body: dict[str, Any]) -> dict[str, Any]:
    """Apply a partial Connections update.

    Secret fields accept ``None`` (unchanged), a non-empty string (set), or ``""``
    (clear). Emails and MCP replace when the key is present.
    """
    data = _load_yaml()
    if not data and not os.path.isfile(PROFILE_PATH):
        raise ValueError("Save your profile first (name + email), then configure connections.")

    platforms = data.get("platforms") if isinstance(data.get("platforms"), dict) else {}
    linkedin = dict(platforms.get("linkedin") or {}) if isinstance(platforms.get("linkedin"), dict) else {}
    naukri = dict(platforms.get("naukri") or {}) if isinstance(platforms.get("naukri"), dict) else {}
    changed_profile = False

    if "linkedin_email" in body and body["linkedin_email"] is not None:
        linkedin["email"] = str(body["linkedin_email"]).strip()
        changed_profile = True
    if "naukri_email" in body and body["naukri_email"] is not None:
        naukri["email"] = str(body["naukri_email"]).strip()
        changed_profile = True
    if "gmail_sender" in body and body["gmail_sender"] is not None:
        email_cfg = data.get("email") if isinstance(data.get("email"), dict) else {}
        email_cfg = dict(email_cfg)
        email_cfg.setdefault("smtp_host", "smtp.gmail.com")
        email_cfg.setdefault("smtp_port", 587)
        email_cfg.setdefault("max_per_run", 10)
        email_cfg["sender"] = str(body["gmail_sender"]).strip()
        data["email"] = email_cfg
        changed_profile = True

    if "linkedin_password" in body:
        _write_secret("SHORTLISTR_LINKEDIN_PASSWORD", body.get("linkedin_password"))
    if "naukri_password" in body:
        _write_secret("SHORTLISTR_NAUKRI_PASSWORD", body.get("naukri_password"))
    if "gmail_app_password" in body:
        _write_secret("GMAIL_APP_PASSWORD", body.get("gmail_app_password"))
    if "telegram_bot_token" in body:
        _write_secret("TELEGRAM_BOT_TOKEN", body.get("telegram_bot_token"))
    if "apify_token" in body:
        _write_secret("APIFY_TOKEN", body.get("apify_token"))

    if "apify_enabled" in body and body["apify_enabled"] is not None:
        sources = data.get("sources") if isinstance(data.get("sources"), dict) else {}
        sources = dict(sources)
        enabled = list(sources.get("enabled") or [])
        # Preserve order; normalize for membership checks.
        have = {str(x).strip().lower(): str(x).strip() for x in enabled if str(x).strip()}
        want = bool(body["apify_enabled"])
        if want and "apify" not in have:
            enabled.append("apify")
        elif not want and "apify" in have:
            enabled = [x for x in enabled if str(x).strip().lower() != "apify"]
        sources["enabled"] = enabled
        # Sensible first-run boards if none configured yet.
        apify_cfg = sources.get("apify") if isinstance(sources.get("apify"), dict) else {}
        apify_cfg = dict(apify_cfg)
        if want and not apify_cfg.get("boards"):
            apify_cfg["boards"] = ["naukri", "linkedin", "indeed"]
            apify_cfg.setdefault("max_pairs", 1)
            apify_cfg.setdefault("limit", 40)
        sources["apify"] = apify_cfg
        data["sources"] = sources
        changed_profile = True

    if "mcp_servers" in body and body["mcp_servers"] is not None:
        servers = body["mcp_servers"]
        if not isinstance(servers, list):
            raise ValueError("mcp_servers must be a list")
        cleaned: list[dict[str, Any]] = []
        for raw in servers:
            if not isinstance(raw, dict):
                continue
            name = str(raw.get("name") or "").strip()
            if not name:
                raise ValueError("Each MCP server needs a name")
            kind = str(raw.get("type") or raw.get("transport") or "stdio").strip().lower()
            if kind not in ("stdio", "http"):
                raise ValueError(f"MCP server '{name}': type must be stdio or http")
            entry: dict[str, Any] = {"name": name, "type": kind}
            if kind == "stdio":
                cmd = str(raw.get("command") or "").strip()
                if not cmd:
                    raise ValueError(f"MCP server '{name}': command is required for stdio")
                entry["command"] = cmd
                args = raw.get("args") or []
                if isinstance(args, str):
                    args = [a for a in args.split() if a]
                if not isinstance(args, list):
                    raise ValueError(f"MCP server '{name}': args must be a list")
                entry["args"] = [str(a) for a in args]
            else:
                url = str(raw.get("url") or "").strip()
                if not url:
                    raise ValueError(f"MCP server '{name}': url is required for http")
                entry["url"] = url
            ref = str(raw.get("secret_ref") or "").strip()
            if ref:
                entry["secret_ref"] = ref
            cleaned.append(entry)
        data["mcp_servers"] = cleaned
        changed_profile = True

    if changed_profile:
        platforms["linkedin"] = linkedin
        platforms["naukri"] = naukri
        data["platforms"] = platforms
        _dump_yaml(data)

    # Passwords live in the keychain / env; emails + MCP in the profile. Either
    # way the running process must re-read so apply-assist uses the new values
    # without an API restart.
    try:
        from config import reload_discovery_config

        reload_discovery_config()
    except Exception:
        pass

    return get_connections_for_ui()


def save_gmail_credentials_json(raw: bytes | str) -> dict[str, Any]:
    """Accept the JSON file Google gives you when you create an OAuth client.

    Non-technical path: download from Google → upload here. No renaming or
    dragging files into the repo by hand.
    """
    import json

    text = raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else str(raw)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError("That file is not valid JSON. Download it again from Google Cloud.") from e

    # Google issues either {"installed": {...}} or {"web": {...}}. Desktop
    # clients use "installed"; either shape is fine as long as client_id exists.
    client = data.get("installed") or data.get("web") or data
    if not isinstance(client, dict) or not client.get("client_id"):
        raise ValueError(
            "This does not look like a Google OAuth client file. "
            "In Google Cloud: APIs & Services → Credentials → Create OAuth client "
            "→ Desktop app → Download JSON."
        )

    creds_path, _ = _gmail_paths()
    os.makedirs(os.path.dirname(creds_path) or ".", exist_ok=True)
    with open(creds_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(data, indent=2))
    return get_connections_for_ui()


def connect_gmail_oauth() -> dict[str, Any]:
    """Open a browser so the user can approve Gmail access — no terminal.

    Blocks until Google redirects back (local loopback). Local-first only: the
    API and the browser must be on the same machine.
    """
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as e:
        raise RuntimeError(
            "Google sign-in libraries are missing. Quit and reopen Shortlistr so it can "
            "finish installing packages."
        ) from e

    from config import GMAIL_SCOPES

    creds_path, token_path = _gmail_paths()
    if not os.path.isfile(creds_path):
        raise FileNotFoundError(
            "Upload your Google credentials file first (the JSON Google lets you download)."
        )

    if os.path.isfile(token_path):
        try:
            os.remove(token_path)
        except OSError:
            pass

    flow = InstalledAppFlow.from_client_secrets_file(creds_path, GMAIL_SCOPES)
    # Opens the system browser; user signs in; we get the token on localhost.
    creds = flow.run_local_server(port=0, open_browser=True)
    with open(token_path, "wb") as f:
        import pickle

        pickle.dump(creds, f)
    return get_connections_for_ui()


def disconnect_gmail_oauth() -> dict[str, Any]:
    """Forget the saved Gmail sign-in (keeps the uploaded credentials file)."""
    _, token_path = _gmail_paths()
    try:
        os.remove(token_path)
    except OSError:
        pass
    return get_connections_for_ui()


def install_playwright_chromium() -> dict[str, Any]:
    """Install Playwright + Chromium from the dashboard — no terminal required.

    After ``make start`` / first install, the user must never be told to run
    ``playwright install`` by hand. This is the only supported path for a missing
    browser binary (and for a missing ``playwright`` pip package).
    """
    # 1. Ensure the Python package is importable (pip may have been skipped or
    #    the venv wiped without reinstalling deps).
    try:
        import playwright  # noqa: F401
    except ImportError:
        try:
            pip = subprocess.run(
                [sys.executable, "-m", "pip", "install", "playwright"],
                cwd=SHORTLISTR_ROOT,
                capture_output=True,
                text=True,
                timeout=300,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "Installing the playwright package timed out"}
        if pip.returncode != 0:
            err = (pip.stderr or pip.stdout or "pip install playwright failed").strip()
            return {"ok": False, "error": err[-500:]}

    # 2. Download the Chromium browser binary.
    try:
        result = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            cwd=SHORTLISTR_ROOT,
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
    except FileNotFoundError:
        return {"ok": False, "error": "Python not found — restart Shortlistr from make start"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Chromium download timed out after 10 minutes"}

    status = _playwright_status()
    if result.returncode != 0 and not status["installed"]:
        err = (result.stderr or result.stdout or "install failed").strip()
        return {"ok": False, "error": err[-500:], "playwright": status}
    if not status["installed"]:
        return {
            "ok": False,
            "error": "Install finished but Chromium was not detected. Try again from Connections.",
            "playwright": status,
        }
    return {"ok": True, "playwright": status}


def ensure_local_ai_from_ui(*, force: bool = False, model: str | None = None) -> dict[str, Any]:
    """One-click Local AI setup from Connections — no terminal."""
    from llm.local_ai import ensure_local_ai_async, local_ai_status

    ensure_local_ai_async(force=force, model=model)
    return {"ok": True, "local_ai": local_ai_status()}
