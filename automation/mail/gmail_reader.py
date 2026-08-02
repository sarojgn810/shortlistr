"""Gmail-backed mailbox reader.

Wraps the existing OAuth service and header/body decoding rather than
reimplementing them — that code is well-tuned and this is a refactor, not a
rewrite. The one thing it owns is turning "recent mail from these senders" into
a Gmail `q`, which is what keeps the filter server-side.
"""

from __future__ import annotations

import logging
from typing import Sequence

from mail.base import Message

logger = logging.getLogger(__name__)


class GmailReader:
    name = "gmail"

    def __init__(self, service=None):
        self._service = service

    @property
    def service(self):
        if self._service is None:
            from processors.email_monitor import _get_gmail_service

            self._service = _get_gmail_service()
        return self._service

    @staticmethod
    def available() -> bool:
        from processors.email_monitor import _get_gmail_service

        return _get_gmail_service() is not None

    def search_recent(self, *, days: int, senders: Sequence[str] = ()) -> list[str]:
        svc = self.service
        if svc is None:
            return []
        q = f"newer_than:{int(days)}d"
        if senders:
            q += " (" + " OR ".join(f"from:{s}" for s in senders) + ")"

        ids: list[str] = []
        page_token = None
        while len(ids) < 100:
            req = {"userId": "me", "q": q, "maxResults": min(50, 100 - len(ids))}
            if page_token:
                req["pageToken"] = page_token
            try:
                result = svc.users().messages().list(**req).execute()
            except Exception as e:
                logger.warning("Gmail list failed: %s", e)
                break
            ids.extend(m["id"] for m in (result.get("messages") or []))
            page_token = result.get("nextPageToken")
            if not page_token:
                break
        return ids

    def fetch(self, message_id: str) -> Message | None:
        from processors.email_monitor import _decode_body, _get_header

        svc = self.service
        if svc is None:
            return None
        try:
            raw = svc.users().messages().get(
                userId="me", id=message_id, format="full"
            ).execute()
        except Exception as e:
            logger.debug("Could not fetch message %s: %s", message_id, e)
            return None
        return Message(
            id=message_id,
            sender=_get_header(raw, "From"),
            subject=_get_header(raw, "Subject"),
            body=_decode_body(raw),
        )
