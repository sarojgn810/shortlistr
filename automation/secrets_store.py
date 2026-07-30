"""OS keychain-backed secret store with a transparent .env fallback.

Secrets (LLM API keys, email app-passwords, platform passwords, OAuth tokens)
belong in the OS keychain — not plaintext .env. This module is the single
indirection the rest of the app reads/writes secrets through:

    reads  → keychain first, then environment/.env (back-compat, headless/dev)
    writes → keychain when available, else process env

macOS Keychain / Windows Credential Locker / Linux libsecret are used via the
`keyring` package. On a headless box with no backend, calls degrade to env.
"""

from __future__ import annotations

import logging
import os
import re

logger = logging.getLogger(__name__)

SERVICE = "shortlistr"

# Secret env var names shortlistr uses (for one-time .env → keychain migration).
KNOWN_SECRETS = (
    "SHORTLISTR_LLM_API_KEY",
    "GMAIL_APP_PASSWORD",
    "SHORTLISTR_EMAIL_PASSWORD",
    "LINKEDIN_PASSWORD",
    "SHORTLISTR_LINKEDIN_PASSWORD",
    "NAUKRI_PASSWORD",
    "SHORTLISTR_NAUKRI_PASSWORD",
    "TELEGRAM_BOT_TOKEN",
)


def _keyring():
    """Return the keyring module if a usable backend is present, else None.

    Forced off under pytest or when SHORTLISTR_NO_KEYRING is set, so tests and
    headless/CI runs use the process-env fallback and never touch the real keychain.
    """
    if os.environ.get("SHORTLISTR_NO_KEYRING") or "PYTEST_CURRENT_TEST" in os.environ:
        return None
    try:
        import keyring
        from keyring.backends.fail import Keyring as FailKeyring

        if isinstance(keyring.get_keyring(), FailKeyring):
            return None
        return keyring
    except Exception:
        return None


def get_secret(name: str, default: str = "") -> str:
    """Read a secret: keychain first, then environment/.env."""
    kr = _keyring()
    if kr is not None:
        try:
            val = kr.get_password(SERVICE, name)
            if val:
                return val
        except Exception as e:  # backend hiccup — fall back to env
            logger.debug("keyring get %s failed: %s", name, e)
    return os.environ.get(name, default)


def set_secret(name: str, value: str) -> bool:
    """Store a secret in the keychain (and process env for this run). Returns True if persisted to keychain."""
    kr = _keyring()
    if kr is not None:
        try:
            kr.set_password(SERVICE, name, value)
            os.environ[name] = value
            return True
        except Exception as e:
            logger.warning("keyring set %s failed, using env only: %s", name, e)
    os.environ[name] = value
    return False


def delete_secret(name: str) -> None:
    kr = _keyring()
    if kr is not None:
        try:
            kr.delete_password(SERVICE, name)
        except Exception:
            pass
    os.environ.pop(name, None)


def has_secret(name: str) -> bool:
    return bool(get_secret(name))


def migrate_env_to_keyring(env_path: str) -> list[str]:
    """Move plaintext secrets from a .env file into the keychain, blanking each line.

    Idempotent and safe: only known secret keys with a non-empty value are moved,
    and only when a keychain backend is available. The .env keeps the key name as
    a blank line so the file still documents what is configured.
    """
    if not os.path.isfile(env_path):
        return []
    kr = _keyring()
    if kr is None:
        return []

    moved: list[str] = []
    out: list[str] = []
    changed = False
    for line in open(env_path, encoding="utf-8").read().splitlines():
        m = re.match(r"^([A-Z0-9_]+)=(.*)$", line)
        if m and m.group(1) in KNOWN_SECRETS:
            name, value = m.group(1), m.group(2).strip()
            if value.startswith("#"):
                # Self-heal a line poisoned by the old buggy migration
                # (KEY=  # moved...): blank it so dotenv can't load the marker
                # as a value. Do not treat it as a real secret.
                out.append(f"{name}=")
                changed = True
                continue
            if value:
                try:
                    kr.set_password(SERVICE, name, value)
                    out.append(f"{name}=")  # blank, no inline comment to re-match
                    moved.append(name)
                    changed = True
                    continue
                except Exception:
                    pass  # leave the line untouched if the move failed
        out.append(line)

    if changed:
        with open(env_path, "w", encoding="utf-8") as f:
            f.write("\n".join(out).rstrip() + "\n")
    return moved
