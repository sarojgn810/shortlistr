"""Generic IMAP/SMTP channel — covers Outlook and any standard mailbox.

Credentials come from the OS keychain (secrets_store), never config plaintext.
"""

from __future__ import annotations

import logging
import os
import smtplib
import ssl
from email.message import EmailMessage

from channels.base import Channel, SendResult
from secrets_store import get_secret

logger = logging.getLogger(__name__)


class SmtpImapChannel(Channel):
    name = "smtp_imap"

    def __init__(
        self,
        *,
        smtp_host: str,
        smtp_port: int = 587,
        username: str = "",
        password_secret: str = "SHORTLISTR_EMAIL_PASSWORD",
    ):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.username = username
        self.password_secret = password_secret

    def send(self, to, subject, body, *, attachments=None, dry_run=False) -> SendResult:
        if dry_run:
            return SendResult(ok=True, detail="dry-run")
        password = get_secret(self.password_secret)
        if not (self.username and password):
            return SendResult(ok=False, detail="missing SMTP username/password")

        msg = EmailMessage()
        msg["From"] = self.username
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body if isinstance(body, str) else str(body))
        for path in attachments or []:
            try:
                with open(path, "rb") as f:
                    data = f.read()
                msg.add_attachment(
                    data, maintype="application", subtype="octet-stream",
                    filename=os.path.basename(path),
                )
            except Exception as e:
                logger.warning("attachment %s skipped: %s", path, e)

        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=30) as s:
                s.starttls(context=ssl.create_default_context())
                s.login(self.username, password)
                s.send_message(msg)
            return SendResult(ok=True)
        except Exception as e:
            logger.warning("SMTP send failed: %s", e)
            return SendResult(ok=False, detail=str(e))
