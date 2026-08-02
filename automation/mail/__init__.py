"""Pick the user's mailbox. Gmail if it is already connected, else IMAP.

Auto-detection on purpose: an existing install has a Gmail token and must keep
working with no config change, and a new user on Outlook should only have to fill
in Connections. Nobody should have to name their provider twice.
"""

from __future__ import annotations

import logging
import os

from mail.base import MailboxReader, MailboxUnavailable, Message

logger = logging.getLogger(__name__)

__all__ = ["MailboxReader", "MailboxUnavailable", "Message", "get_reader",
           "mailbox_status"]

DEFAULT_IMAP_PORT = 993

# Hosts we can infer, so a user only types their address. Anything else needs the
# server filled in by hand — guessing wrong is worse than asking.
KNOWN_IMAP_HOSTS = {
    "outlook.com": "outlook.office365.com",
    "hotmail.com": "outlook.office365.com",
    "live.com": "outlook.office365.com",
    "office365.com": "outlook.office365.com",
    "yahoo.com": "imap.mail.yahoo.com",
    "fastmail.com": "imap.fastmail.com",
    "icloud.com": "imap.mail.me.com",
    "me.com": "imap.mail.me.com",
    "zoho.com": "imap.zoho.com",
    "gmx.com": "imap.gmx.com",
    "aol.com": "imap.aol.com",
}


def _saved_mailbox_config() -> dict:
    """What Connections wrote. Env vars still win, for headless and CI runs."""
    try:
        from connections_store import _load_yaml

        cfg = (_load_yaml() or {}).get("mailbox")
        return cfg if isinstance(cfg, dict) else {}
    except Exception:
        return {}


def _imap_settings() -> dict:
    from secrets_store import get_secret

    saved = _saved_mailbox_config()
    user = (os.environ.get("SHORTLISTR_IMAP_USER")
            or os.environ.get("SHORTLISTR_EMAIL_ADDRESS")
            or str(saved.get("imap_user") or "")).strip()
    host = (os.environ.get("SHORTLISTR_IMAP_HOST")
            or str(saved.get("imap_host") or "")).strip()
    if not host and "@" in user:
        host = KNOWN_IMAP_HOSTS.get(user.rsplit("@", 1)[1].lower(), "")
    try:
        port = int(os.environ.get("SHORTLISTR_IMAP_PORT")
                   or saved.get("imap_port") or DEFAULT_IMAP_PORT)
    except (TypeError, ValueError):
        port = DEFAULT_IMAP_PORT
    return {
        "host": host,
        "user": user,
        "password": get_secret("SHORTLISTR_EMAIL_PASSWORD"),
        "port": port,
        "folder": os.environ.get("SHORTLISTR_IMAP_FOLDER")
        or str(saved.get("imap_folder") or "") or "INBOX",
    }


def _configured_provider() -> str:
    return (os.environ.get("SHORTLISTR_MAIL_PROVIDER")
            or str(_saved_mailbox_config().get("provider") or "")).strip().lower()


def get_reader() -> MailboxReader | None:
    """The user's mailbox, or None if they have not connected one.

    None is not an error: email discovery is optional, and a user with no
    mailbox connected should simply get no email-sourced jobs — never a crash
    and never a stack trace in a scan.
    """
    from mail.gmail_reader import GmailReader
    from mail.imap_reader import ImapReader

    choice = _configured_provider()

    if choice in ("", "auto", "gmail"):
        try:
            if GmailReader.available():
                return GmailReader()
        except Exception as e:
            logger.debug("Gmail unavailable: %s", e)
        if choice == "gmail":
            return None

    if choice in ("", "auto", "imap"):
        settings = _imap_settings()
        if settings["host"] and settings["user"] and settings["password"]:
            try:
                return ImapReader(**settings)
            except MailboxUnavailable as e:
                logger.warning("%s", e)
        elif choice == "imap":
            logger.warning(
                "IMAP selected but not configured — add the address, server and "
                "app password under Connections."
            )
    return None


def mailbox_status() -> dict:
    """What Connections should show. Never raises, never leaks the password."""
    from mail.gmail_reader import GmailReader

    settings = _imap_settings()
    try:
        gmail_ok = GmailReader.available()
    except Exception:
        gmail_ok = False
    reader = None
    try:
        reader = get_reader()
    except Exception:
        pass
    return {
        "connected": reader is not None,
        "provider": getattr(reader, "name", None),
        "gmail_available": gmail_ok,
        "imap_host": settings["host"],
        "imap_user": settings["user"],
        "imap_password_set": bool(settings["password"]),
    }
