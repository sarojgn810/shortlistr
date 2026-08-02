"""Channel protocol — uniform communication actions across providers.

Mirrors the source-adapter pattern (sources/base.py). A Channel exposes
read_inbox / draft_reply / send so Gmail, IMAP/SMTP, Outlook or an MCP-backed
provider are interchangeable. Outbound `send` is registered as a submit-class
tool, so it always passes the F2 permission gate.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class SendResult:
    ok: bool
    detail: str = ""


class Channel(ABC):
    name: str = "channel"

    @abstractmethod
    def send(
        self,
        to: str,
        subject: str,
        body: str,
        *,
        attachments: list[str] | None = None,
        dry_run: bool = False,
    ) -> SendResult:
        ...

    def read_inbox(self, *, max_messages: int = 50) -> list[dict]:
        """Return recent inbox items (provider-specific shape). Default: none."""
        return []

    def draft_reply(self, to: str, subject: str, body: str) -> dict:
        """Return a draft payload without sending (no side effect)."""
        return {"to": to, "subject": subject, "body": body}

    def health_check(self) -> bool:
        return True
