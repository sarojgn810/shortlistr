"""IMAP-backed mailbox reader — Outlook, Yahoo, Proton Bridge, Fastmail, any host.

Read-only by construction: the mailbox is opened with `select(readonly=True)`, so
nothing here can mark a message read, move it, or delete it. Someone's inbox is
not ours to modify, and a job search should never be the reason mail changed.

Sender filtering is done over a single batched header fetch rather than an IMAP
SEARCH. `SEARCH` only ORs two terms at a time, so 29 alert senders would nest 28
deep — unreadable, and rejected outright by some servers. Fetching headers for a
week of mail is one round trip and lets the same sender list work everywhere.
"""

from __future__ import annotations

import email
import email.policy
import imaplib
import logging
import re
from datetime import datetime, timedelta
from email.header import decode_header, make_header
from typing import Sequence

from mail.base import Message, MailboxUnavailable

logger = logging.getLogger(__name__)

# A week of mail in one header fetch is fine; a mailbox that huge is a signal to
# narrow the window, not to page forever.
MAX_MESSAGES = 400


def _decode(value: str) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def _body_of(msg: email.message.Message) -> str:
    """Prefer HTML — job digests put their links in markup, not the text part."""
    html, text = "", ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_maintype() == "multipart":
                continue
            if part.get_filename():
                continue
            try:
                payload = part.get_payload(decode=True) or b""
                decoded = payload.decode(part.get_content_charset() or "utf-8", "replace")
            except Exception:
                continue
            if part.get_content_type() == "text/html":
                html += decoded
            elif part.get_content_type() == "text/plain":
                text += decoded
    else:
        try:
            payload = msg.get_payload(decode=True) or b""
            decoded = payload.decode(msg.get_content_charset() or "utf-8", "replace")
        except Exception:
            decoded = ""
        if msg.get_content_type() == "text/html":
            html = decoded
        else:
            text = decoded
    return html or text


class ImapReader:
    name = "imap"

    def __init__(self, *, host: str, user: str, password: str,
                 port: int = 993, folder: str = "INBOX"):
        if not (host and user and password):
            raise MailboxUnavailable(
                "IMAP mailbox is not configured — add the host, address and app "
                "password in the dashboard under Connections."
            )
        self.host, self.user, self.password = host, user, password
        self.port, self.folder = port, folder
        self._conn: imaplib.IMAP4_SSL | None = None
        self._headers: dict[str, tuple[str, str]] = {}

    # ── connection ───────────────────────────────────────────────────────────

    def _connect(self) -> imaplib.IMAP4_SSL:
        if self._conn is not None:
            return self._conn
        try:
            conn = imaplib.IMAP4_SSL(self.host, self.port)
            conn.login(self.user, self.password)
            # readonly: reading mail must never mark it read or move it.
            conn.select(self.folder, readonly=True)
        except imaplib.IMAP4.error as e:
            raise MailboxUnavailable(
                f"Could not sign in to {self.host} as {self.user}. Most providers "
                f"need an app-specific password rather than your normal one. ({e})"
            ) from e
        except OSError as e:
            raise MailboxUnavailable(f"Could not reach {self.host}:{self.port} ({e})") from e
        self._conn = conn
        return conn

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
                self._conn.logout()
            except Exception:
                pass
            self._conn = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ── reading ──────────────────────────────────────────────────────────────

    def search_recent(self, *, days: int, senders: Sequence[str] = ()) -> list[str]:
        conn = self._connect()
        since = (datetime.now() - timedelta(days=max(1, int(days)))).strftime("%d-%b-%Y")
        try:
            typ, data = conn.search(None, "SINCE", since)
        except imaplib.IMAP4.error as e:
            logger.warning("IMAP search failed: %s", e)
            return []
        if typ != "OK":
            return []

        uids = (data[0] or b"").split()
        if not uids:
            return []
        uids = uids[-MAX_MESSAGES:]

        # One fetch for every header, then filter locally. See module docstring
        # for why this is not an IMAP SEARCH with 28 nested ORs.
        try:
            typ, raw = conn.fetch(
                b",".join(uids), "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT)])"
            )
        except imaplib.IMAP4.error as e:
            logger.warning("IMAP header fetch failed: %s", e)
            return []
        if typ != "OK":
            return []

        self._headers = {}
        keep: list[str] = []
        for item in raw or []:
            if not isinstance(item, tuple) or len(item) < 2:
                continue
            prefix = item[0].decode("utf-8", "replace") if isinstance(item[0], bytes) else str(item[0])
            m = re.match(r"^(\d+)\s", prefix)
            if not m:
                continue
            uid = m.group(1)
            parsed = email.message_from_bytes(item[1], policy=email.policy.default)
            sender = _decode(parsed.get("From", ""))
            subject = _decode(parsed.get("Subject", ""))
            self._headers[uid] = (sender, subject)
            if senders and not any(s.lower() in sender.lower() for s in senders):
                continue
            keep.append(uid)
        return keep

    def fetch(self, message_id: str) -> Message | None:
        conn = self._connect()
        try:
            typ, raw = conn.fetch(str(message_id).encode(), "(BODY.PEEK[])")
        except imaplib.IMAP4.error as e:
            logger.debug("IMAP fetch %s failed: %s", message_id, e)
            return None
        if typ != "OK" or not raw:
            return None
        for item in raw:
            if isinstance(item, tuple) and len(item) >= 2:
                parsed = email.message_from_bytes(item[1], policy=email.policy.default)
                sender, subject = self._headers.get(
                    str(message_id), (_decode(parsed.get("From", "")),
                                      _decode(parsed.get("Subject", ""))))
                return Message(
                    id=str(message_id),
                    sender=sender or _decode(parsed.get("From", "")),
                    subject=subject or _decode(parsed.get("Subject", "")),
                    body=_body_of(parsed),
                )
        return None
