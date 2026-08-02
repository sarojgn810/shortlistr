"""Reading mail must not require Gmail.

Job-alert ingestion and outcome capture both read the user's inbox. Both called
the Gmail API directly, so a cloner on Outlook, Yahoo, Proton or Fastmail got
neither — 30% of a pipeline and all automatic rejection/interview/offer tracking,
missing, with nothing to say why.
"""

from __future__ import annotations

import email.message
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))


# ── provider selection ───────────────────────────────────────────────────────

@pytest.fixture
def clean_env(monkeypatch):
    for var in ("SHORTLISTR_MAIL_PROVIDER", "SHORTLISTR_IMAP_HOST",
                "SHORTLISTR_IMAP_USER", "SHORTLISTR_IMAP_PORT",
                "SHORTLISTR_EMAIL_ADDRESS", "SHORTLISTR_IMAP_FOLDER"):
        monkeypatch.delenv(var, raising=False)


def test_no_mailbox_configured_is_not_an_error(clean_env, monkeypatch):
    """Email discovery is optional — an unconnected user gets no jobs, no crash."""
    import mail
    from mail.gmail_reader import GmailReader

    monkeypatch.setattr(GmailReader, "available", staticmethod(lambda: False))
    monkeypatch.setattr("secrets_store.get_secret", lambda *a, **k: "")
    assert mail.get_reader() is None


def test_gmail_is_preferred_when_already_connected(clean_env, monkeypatch):
    """An existing install must keep working with no config change."""
    import mail
    from mail.gmail_reader import GmailReader

    monkeypatch.setattr(GmailReader, "available", staticmethod(lambda: True))
    reader = mail.get_reader()
    assert reader is not None and reader.name == "gmail"


def test_imap_is_used_when_gmail_is_not_connected(clean_env, monkeypatch):
    import mail
    from mail.gmail_reader import GmailReader

    monkeypatch.setattr(GmailReader, "available", staticmethod(lambda: False))
    monkeypatch.setenv("SHORTLISTR_IMAP_USER", "me@outlook.com")
    monkeypatch.setattr("secrets_store.get_secret", lambda *a, **k: "app-password")
    monkeypatch.setattr("mail.imap_reader.ImapReader._connect", lambda self: None)

    reader = mail.get_reader()
    assert reader is not None and reader.name == "imap"


def test_common_providers_do_not_need_a_server_typed_in(clean_env, monkeypatch):
    """A user should only have to give their address and an app password."""
    import mail

    monkeypatch.setattr("secrets_store.get_secret", lambda *a, **k: "pw")
    for address, expected in [
        ("me@outlook.com", "outlook.office365.com"),
        ("me@hotmail.com", "outlook.office365.com"),
        ("me@yahoo.com", "imap.mail.yahoo.com"),
        ("me@fastmail.com", "imap.fastmail.com"),
        ("me@icloud.com", "imap.mail.me.com"),
    ]:
        monkeypatch.setenv("SHORTLISTR_IMAP_USER", address)
        assert mail._imap_settings()["host"] == expected


def test_an_unknown_domain_needs_the_server_given(clean_env, monkeypatch):
    """Guessing a host wrong is worse than asking for it."""
    import mail

    monkeypatch.setattr("secrets_store.get_secret", lambda *a, **k: "pw")
    monkeypatch.setenv("SHORTLISTR_IMAP_USER", "me@some-company.co.in")
    assert mail._imap_settings()["host"] == ""


def test_status_never_leaks_the_password(clean_env, monkeypatch):
    import mail

    monkeypatch.setattr("secrets_store.get_secret", lambda *a, **k: "super-secret")
    monkeypatch.setenv("SHORTLISTR_IMAP_USER", "me@outlook.com")
    status = mail.mailbox_status()
    assert status["imap_password_set"] is True
    assert "super-secret" not in str(status)


def test_imap_without_credentials_says_what_to_do(clean_env):
    from mail.base import MailboxUnavailable
    from mail.imap_reader import ImapReader

    with pytest.raises(MailboxUnavailable) as exc:
        ImapReader(host="", user="", password="")
    assert "Connections" in str(exc.value)


# ── IMAP body decoding ───────────────────────────────────────────────────────

def _multipart(html: str, text: str) -> email.message.Message:
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    msg = MIMEMultipart("alternative")
    msg["From"] = "hirist.tech <info@hirist.tech>"
    msg["Subject"] = "Jobs for you"
    msg.attach(MIMEText(text, "plain"))
    msg.attach(MIMEText(html, "html"))
    return msg


def test_html_part_wins_over_plain_text():
    """Digests put their job links in the markup, not the text alternative."""
    from mail.imap_reader import _body_of

    body = _body_of(_multipart("<a href='https://x.test/j/1'>SRE</a>", "plain fallback"))
    assert "x.test/j/1" in body


def test_a_plain_text_only_message_still_decodes():
    from email.mime.text import MIMEText

    from mail.imap_reader import _body_of

    assert "hello" in _body_of(MIMEText("hello", "plain"))


def test_encoded_headers_are_decoded():
    from mail.imap_reader import _decode

    assert _decode("=?utf-8?B?SGVsbG8=?=") == "Hello"
    assert _decode("") == ""


# ── the reader contract ──────────────────────────────────────────────────────

def test_message_sender_matching_is_case_insensitive():
    from mail.base import Message

    msg = Message(id="1", sender="Hirist.Tech <INFO@Hirist.TECH>")
    assert msg.is_from(["hirist.tech"])
    assert not msg.is_from(["naukri.com"])


def test_outcome_capture_works_on_any_provider(monkeypatch):
    """Rejection / interview / offer tracking must not be Gmail-only either."""
    from mail.base import Message
    from outcomes import capture

    class Reader:
        name = "imap"

        def search_recent(self, *, days, senders=()):
            return ["m1"]

        def fetch(self, mid):
            return Message(id=mid, sender="talent@acme.com",
                           subject="Update on your application",
                           body="Unfortunately we will not be moving forward.")

    seen = {}
    monkeypatch.setattr(capture, "process_messages",
                        lambda msgs, **kw: seen.setdefault("msgs", msgs) or [])
    capture.process_inbox(reader=Reader())
    assert seen["msgs"][0]["sender"] == "talent@acme.com"
    assert "not be moving forward" in seen["msgs"][0]["body"]


def test_email_sourced_rows_are_verified_whatever_the_provider():
    """Gating on 'gmail' let every other provider's rows through unchecked."""
    from processors.gmail_verify import is_email_source

    for source in ("gmail", "Gmail", "email", "imap", "outlook"):
        assert is_email_source(source), source
    for source in ("LinkedIn", "Workday", "Greenhouse", "", None):
        assert not is_email_source(source)


# ── what Connections shows ───────────────────────────────────────────────────

def test_connections_reports_the_mailbox_that_will_actually_be_used(monkeypatch):
    """A non-Gmail user must not be left guessing why they get no email jobs."""
    import connections_store as cs

    monkeypatch.setattr(cs, "_gmail_oauth_status",
                        lambda: {"credentials_present": False, "token_present": False})
    monkeypatch.setattr(cs, "_secret_set", lambda name: name == "SHORTLISTR_EMAIL_PASSWORD")
    monkeypatch.setattr(cs, "_load_yaml", lambda: {
        "mailbox": {"imap_user": "me@outlook.com"}
    })

    status = cs._mailbox_status()
    assert status["imap_host"] == "outlook.office365.com", "server was not inferred"
    assert status["imap_ready"] is True
    assert status["active"] == "imap"


def test_gmail_still_wins_when_its_token_is_present(monkeypatch):
    import connections_store as cs

    monkeypatch.setattr(cs, "_gmail_oauth_status",
                        lambda: {"credentials_present": True, "token_present": True})
    monkeypatch.setattr(cs, "_secret_set", lambda name: True)
    monkeypatch.setattr(cs, "_load_yaml", lambda: {})
    assert cs._mailbox_status()["active"] == "gmail"


def test_nothing_connected_reports_no_active_mailbox(monkeypatch):
    import connections_store as cs

    monkeypatch.setattr(cs, "_gmail_oauth_status",
                        lambda: {"credentials_present": False, "token_present": False})
    monkeypatch.setattr(cs, "_secret_set", lambda name: False)
    monkeypatch.setattr(cs, "_load_yaml", lambda: {})
    status = cs._mailbox_status()
    assert status["active"] is None and status["imap_ready"] is False


def test_saving_imap_settings_keeps_the_password_out_of_config(monkeypatch, tmp_path):
    import connections_store as cs

    written = {}
    profile = tmp_path / "profile.yml"
    profile.write_text("candidate:\n  name: Test\n  email: t@example.com\n")
    monkeypatch.setattr(cs, "_write_secret", lambda k, v: written.update({k: v}))
    monkeypatch.setattr(cs, "PROFILE_PATH", str(profile))

    cs.save_connections_from_ui({
        "mailbox_imap_user": "me@outlook.com",
        "mailbox_imap_host": "outlook.office365.com",
        "mailbox_password": "app-specific-password",
    })

    assert written["SHORTLISTR_EMAIL_PASSWORD"] == "app-specific-password"
    saved = profile.read_text()
    assert "app-specific-password" not in saved, "password was written to config"
    assert "me@outlook.com" in saved
