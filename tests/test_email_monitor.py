"""Unit tests for Gmail job-alert URL extraction."""

import base64

from automation.processors.email_monitor import (
    JOB_ALERT_SENDERS,
    _canonicalize_job_url,
    _decode_body,
    _extract_urls_from_text,
    _unwrap_tracking_url,
)


def test_hirist_in_alert_senders():
    assert any("hirist" in s for s in JOB_ALERT_SENDERS)


def test_unwrap_hirist_click_wrapper():
    raw = (
        "https://postoffice.hirist.tech/CL0/"
        "https:%2F%2Fwww.hirist.tech%2Fj%2Fgenerative-ai-architect-coforge-12345"
        "/1/abcdef12-3456-7890-abcd-ef1234567890"
    )
    out = _unwrap_tracking_url(raw)
    assert "www.hirist.tech/j/generative-ai-architect-coforge-12345" in out
    assert "postoffice" not in out


def test_unwrap_remotive_pstmrk():
    raw = (
        "https://track.pstmrk.it/3s/"
        "jobs.workable.com%2Fview%2Fabc123%2Fazure-data-engineer"
        "/eHy2/tracker"
    )
    out = _unwrap_tracking_url(raw)
    assert out.startswith("https://jobs.workable.com/view/")
    assert "pstmrk" not in out


def test_extract_naukri_jd_path_from_html():
    html = '''
    <a href="https://www.naukri.com/jd/job-listings-sre-chaos-engg-tata-123456">SRE</a>
    <a href="https://www.naukri.com/unsubscribe">skip</a>
    '''
    urls = _extract_urls_from_text(html)
    assert len(urls) == 1
    assert "/jd/job-listings-sre-chaos-engg-tata-123456" in urls[0]


def test_extract_glassdoor_partner_keeps_query():
    html = (
        '<a href="https://www.glassdoor.co.in/partner/jobListing.htm'
        '?pos=101&ao=1136043&s=21&guid=0001&jobListingId=100001">role</a>'
    )
    urls = _extract_urls_from_text(html)
    assert len(urls) == 1
    assert "jobListing.htm" in urls[0]
    assert "jobListingId=100001" in urls[0]


def test_extract_hirist_from_wrapped_href():
    html = (
        '<a href="https://postoffice.hirist.tech/CL0/'
        'https:%2F%2Fwww.hirist.tech%2Fj%2Fagentic-ai-architect-publicis'
        '/1/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee">Apply</a>'
    )
    urls = _extract_urls_from_text(html)
    assert any("hirist.tech/j/agentic-ai-architect-publicis" in u for u in urls)


def test_decode_body_reads_html_only_message():
    html = '<html><a href="https://www.naukri.com/jd/job-listings-devops-999">x</a></html>'
    b64 = base64.urlsafe_b64encode(html.encode()).decode().rstrip("=")
    msg = {
        "payload": {
            "mimeType": "text/html",
            "body": {"data": b64},
            "headers": [],
        }
    }
    body = _decode_body(msg)
    assert "naukri.com/jd/job-listings-devops-999" in body
    urls = _extract_urls_from_text(body)
    assert urls


def test_canonicalize_strips_trailing_punctuation():
    u = _canonicalize_job_url("https://www.hirist.tech/j/role-123).")
    assert u.endswith("role-123")


def test_rejects_board_homepages_and_settings():
    noise = """
    <a href="https://www.naukri.com/">home</a>
    <a href="https://www.naukri.com/mnjuser/settings/communication">settings</a>
    <a href="https://www.hirist.tech/jobfeed/">feed</a>
    <a href="https://www.hirist.tech/course/foo">course</a>
    <a href="https://media.glassdoor.com/logo.png">logo</a>
    <a href="https://www.naukri.com/jd/job-listings-sre-tata-1">keep</a>
    """
    urls = _extract_urls_from_text(noise)
    assert len(urls) == 1
    assert "jd/job-listings-sre-tata-1" in urls[0]


def test_subject_title_hint_strips_digest_suffix():
    from automation.processors.email_monitor import _subject_title_hint, _subject_location_hint

    subj = "Associate Site Reliability Engineer at Shell and 11 more jobs in Bengaluru for you."
    assert "Associate Site Reliability Engineer at Shell" in _subject_title_hint(subj)
    assert "and 11 more" not in _subject_title_hint(subj)
    assert "Bengaluru" in _subject_location_hint(subj)


def test_glassdoor_uses_anchor_text_as_title():
    from automation.processors.email_monitor import _extract_job_links

    html = (
        '<a href="https://www.glassdoor.co.in/partner/jobListing.htm'
        '?pos=101&jobListingId=100001">Senior Site Reliability Engineer</a>'
    )
    links = _extract_job_links(html)
    assert len(links) == 1
    assert links[0][1] == "Senior Site Reliability Engineer"


def test_gmail_alert_query_includes_read_mail():
    from automation.processors.email_monitor import GMAIL_ALERT_QUERY

    assert "is:unread" not in GMAIL_ALERT_QUERY
    assert "newer_than:" in GMAIL_ALERT_QUERY


# ── Sender filtering and re-scan cost ────────────────────────────────────────
#
# A scan spent 42.5s here and returned nothing. Of 100 listed messages, 42 were
# already ingested and skipped, leaving 58 downloaded in full every single run:
# 27 that were not job alerts at all (downloaded just to read the From header)
# and 31 alert mails with genuinely no job link, which were deliberately never
# remembered — so they were re-fetched forever.


def test_alert_query_filters_by_sender_server_side():
    """The From check must happen in Gmail's query, not after the download."""
    from automation.processors.email_monitor import (
        GMAIL_ALERT_QUERY,
        JOB_ALERT_SENDERS,
        _alert_sender_query,
    )

    q = _alert_sender_query()
    assert GMAIL_ALERT_QUERY in q
    assert "from:" in q
    for sender in JOB_ALERT_SENDERS[:5]:
        assert f"from:{sender}" in q
    assert " OR " in q


def test_alert_query_survives_an_empty_sender_list(monkeypatch):
    from automation.processors import email_monitor as em

    monkeypatch.setattr(em, "JOB_ALERT_SENDERS", [])
    assert em._alert_sender_query() == em.GMAIL_ALERT_QUERY
def test_a_message_with_no_links_is_remembered(monkeypatch):
    """Otherwise 'verify your email address' is re-downloaded on every scan."""
    from automation.processors import email_monitor as em

    saved = {}
    monkeypatch.setattr(em, "_load_state", lambda: {})
    monkeypatch.setattr(em, "_save_state", lambda s: saved.update(s))

    em.fetch_alert_job_records(reader=_FakeReader())
    assert saved["empty_ids"] == ["m-empty"], "a dead alert mail was not remembered"
    assert saved["empty_extractor_version"] == em.EXTRACTOR_VERSION


def test_remembered_empty_messages_are_not_refetched(monkeypatch):
    from automation.processors import email_monitor as em

    reader = _FakeReader()
    monkeypatch.setattr(em, "_save_state", lambda s: None)
    monkeypatch.setattr(em, "_load_state", lambda: {
        "empty_ids": ["m-empty"],
        "empty_extractor_version": em.EXTRACTOR_VERSION,
    })

    em.fetch_alert_job_records(reader=reader)
    assert "m-empty" not in reader.fetched, "re-read a message already known to be empty"


def test_bumping_the_extractor_version_re_examines_empty_messages(monkeypatch):
    """A decode or regex fix must not leave digests permanently buried."""
    from automation.processors import email_monitor as em

    reader = _FakeReader()
    monkeypatch.setattr(em, "_save_state", lambda s: None)
    monkeypatch.setattr(em, "_load_state", lambda: {
        "empty_ids": ["m-empty"],
        "empty_extractor_version": em.EXTRACTOR_VERSION - 1,
    })

    em.fetch_alert_job_records(reader=reader)
    assert "m-empty" in reader.fetched, "stale 'empty' verdict was not revisited"


def test_already_ingested_messages_are_still_skipped(monkeypatch):
    from automation.processors import email_monitor as em

    reader = _FakeReader()
    monkeypatch.setattr(em, "_save_state", lambda s: None)
    monkeypatch.setattr(em, "_load_state", lambda: {"processed_ids": ["m-jobs"]})

    em.fetch_alert_job_records(reader=reader)
    assert "m-jobs" not in reader.fetched


def test_any_provider_works_not_just_gmail(monkeypatch):
    """The whole point of the mailbox interface: an IMAP inbox ingests too."""
    from automation.processors import email_monitor as em

    reader = _FakeReader(name="imap")
    monkeypatch.setattr(em, "_save_state", lambda s: None)
    monkeypatch.setattr(em, "_load_state", lambda: {})

    jobs = em.fetch_alert_job_records(reader=reader)
    assert [j.url for j in jobs] == ["https://www.hirist.tech/j/site-reliability-engineer-1"]


def test_a_sender_the_reader_did_not_filter_out_is_still_rejected(monkeypatch):
    """Sender narrowing is a hint; IMAP filters locally and may over-return."""
    from automation.processors import email_monitor as em
    from mail.base import Message

    class Noisy(_FakeReader):
        def fetch(self, mid):
            self.fetched.append(mid)
            return Message(id=mid, sender="newsletter@example.com",
                           subject="Sale", body='<a href="https://x.test/j/1">x</a>')

    monkeypatch.setattr(em, "_save_state", lambda s: None)
    monkeypatch.setattr(em, "_load_state", lambda: {})
    assert em.fetch_alert_job_records(reader=Noisy()) == []


class _FakeReader:
    """A MailboxReader with one alert carrying a job and one carrying nothing."""

    def __init__(self, name="gmail"):
        self.name = name
        self.fetched: list[str] = []

    def search_recent(self, *, days, senders=()):
        return ["m-jobs", "m-empty"]

    def fetch(self, message_id):
        from mail.base import Message

        self.fetched.append(message_id)
        body = (
            '<a href="https://www.hirist.tech/j/site-reliability-engineer-1">SRE</a>'
            if message_id == "m-jobs"
            else "<p>Please verify your email address.</p>"
        )
        return Message(
            id=message_id,
            sender="hirist.tech <info@hirist.tech>",
            subject="Jobs for you",
            body=body,
        )
