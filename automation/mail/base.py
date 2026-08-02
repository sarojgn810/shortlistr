"""What a mailbox has to be able to do, independent of who hosts it.

Job-alert ingestion and application-outcome capture both read the user's mail.
Both used to call the Gmail API directly, so a cloner on Outlook, Yahoo, Proton
or Fastmail got neither — no email discovery and no automatic
rejection/interview/offer tracking — with nothing to tell them why.

The interface is deliberately about *intent* rather than query syntax: "recent
mail from these senders". Gmail expresses that as a `q` string and IMAP as a
SEARCH plus a header pass, and neither of those should leak into a caller.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, Sequence


@dataclass
class Message:
    """One message, already decoded. `body` is text or HTML, whichever was sent."""

    id: str
    sender: str = ""
    subject: str = ""
    body: str = ""
    metadata: dict = field(default_factory=dict)

    def is_from(self, senders: Sequence[str]) -> bool:
        low = (self.sender or "").lower()
        return any(s.lower() in low for s in senders)


class MailboxReader(Protocol):
    """Read-only view of a mailbox. Nothing here sends, deletes, or marks read."""

    name: str

    def search_recent(self, *, days: int, senders: Sequence[str] = ()) -> list[str]:
        """Ids of messages from the last `days`, narrowed to `senders` if given.

        Narrowing is a hint, not a guarantee: a backend that cannot filter by
        sender server-side may return more, and callers re-check with
        `Message.is_from`. Returning *fewer* than asked is never allowed —
        silently dropping a user's job alerts is worse than fetching too much.
        """
        ...

    def fetch(self, message_id: str) -> Message | None:
        """Full message, or None if it vanished or could not be decoded."""
        ...


class MailboxUnavailable(RuntimeError):
    """Raised when no mailbox is configured, or credentials are missing.

    Carries a message meant to be shown to the user, pointing at Connections
    rather than at a shell command.
    """
