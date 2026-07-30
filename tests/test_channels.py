"""Channel abstraction tests (dry-run; no network)."""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))


def test_get_channel_default_and_smtp(monkeypatch):
    monkeypatch.setenv("SHORTLISTR_ROOT", ROOT)
    from channels.gmail import GmailChannel
    from channels.registry import get_channel
    from channels.smtp_imap import SmtpImapChannel

    assert isinstance(get_channel(), GmailChannel)
    assert isinstance(get_channel("smtp_imap"), SmtpImapChannel)


def test_gmail_channel_send_dry_run():
    from channels.gmail import GmailChannel

    res = GmailChannel().send("x@example.com", "Hi", "Body", dry_run=True)
    assert res.ok is True  # dry-run never hits the network


def test_smtp_channel_dry_run_and_missing_creds():
    from channels.smtp_imap import SmtpImapChannel

    ch = SmtpImapChannel(smtp_host="smtp.example.com", username="")
    assert ch.send("x@example.com", "Hi", "Body", dry_run=True).ok is True
    # real send with no username/password fails fast, no connection attempted
    assert ch.send("x@example.com", "Hi", "Body").ok is False


def test_channel_send_is_gated_submit_tool(monkeypatch):
    from agent import registry

    tool = registry.get_tool("channel.send")
    assert tool is not None and tool.side_effect == "submit"
    monkeypatch.setattr(registry, "_autopilot_tools", lambda tenant: [])
    import pytest

    with pytest.raises(registry.PermissionDenied):
        registry.check_permission("channel.send")
    registry.check_permission("channel.send", confirm=True)
