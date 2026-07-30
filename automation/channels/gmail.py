"""Gmail channel — wraps the existing Gmail send + inbox-alert read paths."""

from __future__ import annotations

from channels.base import Channel, SendResult


class GmailChannel(Channel):
    name = "gmail"

    def send(self, to, subject, body, *, attachments=None, dry_run=False) -> SendResult:
        from processors.email_sender import send_application_email

        resume = attachments[0] if attachments else None
        ok = send_application_email(to, subject, body, resume_path=resume, dry_run=dry_run)
        return SendResult(ok=bool(ok), detail="dry-run" if dry_run else "")

    def read_inbox(self, *, max_messages: int = 50) -> list[dict]:
        from processors.email_monitor import fetch_alert_job_records

        try:
            records = fetch_alert_job_records(max_messages=max_messages)
            return [{"type": "job_alert", "record": r} for r in records]
        except Exception:
            return []

    def health_check(self) -> bool:
        from processors.email_monitor import _get_gmail_service

        try:
            return bool(_get_gmail_service())
        except Exception:
            return False
