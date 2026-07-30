"""Channel selection — returns a Channel implementation by name (default Gmail)."""

from __future__ import annotations

from channels.base import Channel
from channels.gmail import GmailChannel


def get_channel(name: str | None = None) -> Channel:
    key = (name or "gmail").lower()
    if key in ("smtp", "imap", "smtp_imap", "outlook"):
        from channels.smtp_imap import SmtpImapChannel
        from config import EMAIL_CONFIG

        return SmtpImapChannel(
            smtp_host=str(EMAIL_CONFIG.get("smtp_host", "smtp.gmail.com")),
            smtp_port=int(EMAIL_CONFIG.get("smtp_port", 587) or 587),
            username=str(EMAIL_CONFIG.get("email", "")),
        )
    return GmailChannel()
