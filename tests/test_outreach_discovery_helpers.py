"""Unit tests for TrySideDoor-style discovery / outreach helpers."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "automation"))

from models.job import JobRecord  # noqa: E402
from models.soft_dedupe import collapse_soft_duplicates, soft_key  # noqa: E402
from sources.ats_fingerprint import fingerprint_url  # noqa: E402
from contacts.email_find import permute_emails, company_domain_guess  # noqa: E402
from export.instantly_csv import rows_from_contacts, to_csv  # noqa: E402


def test_fingerprint_greenhouse_and_smartrecruiters():
    gh = fingerprint_url("https://job-boards.greenhouse.io/acme")
    assert gh and gh["ats_type"] == "greenhouse" and gh["token"] == "acme"
    sr = fingerprint_url("https://careers.smartrecruiters.com/Freshworks")
    assert sr and sr["ats_type"] == "smartrecruiters" and sr["token"] == "Freshworks"
    rt = fingerprint_url("https://doctolib.recruitee.com/")
    assert rt and rt["ats_type"] == "recruitee" and rt["token"] == "doctolib"
    wd = fingerprint_url("https://redhat.wd5.myworkdayjobs.com/jobs")
    assert wd and wd["ats_type"] == "workday" and wd["tenant"] == "redhat"


def test_soft_dedupe_prefers_richer_jd():
    a = JobRecord(
        url="https://boards.greenhouse.io/x/jobs/1",
        source="Greenhouse",
        company="Acme",
        title="SRE",
        location="Bengaluru",
        jd_text="short",
        job_id="a",
    )
    b = JobRecord(
        url="https://www.linkedin.com/jobs/view/2",
        source="LinkedIn",
        company="Acme",
        title="SRE",
        location="Bengaluru",
        jd_text="much longer job description with requirements and stack details here",
        job_id="b",
    )
    assert soft_key("Acme", "SRE", "Bengaluru")
    out = collapse_soft_duplicates([a, b])
    assert len(out) == 1
    assert "longer job description" in (out[0].jd_text or "")
    assert "linkedin.com" in (out[0].url or "")


def test_permute_emails_and_instantly_csv():
    assert company_domain_guess("Stripe", "https://www.stripe.com/careers") == "stripe.com"
    emails = permute_emails("Jane Doe", "acme.com")
    assert "jane.doe@acme.com" in emails
    rows = rows_from_contacts(
        [{"name": "Jane Doe", "email": "jane.doe@acme.com", "linkedin_url": "https://linkedin.com/in/jane"}],
        company="Acme",
        personalization="Saw the SRE role",
    )
    csv = to_csv(rows)
    assert "email,first_name,last_name,company_name" in csv
    assert "jane.doe@acme.com" in csv
    assert "Jane" in csv and "Doe" in csv


# ── Board tokens are slugs, not whatever followed in the HTML ────────────────
#
# The capture was `[^/?#]+`, which stops at a path separator and happily
# swallows the rest of an attribute. Real scans of tracked careers pages came
# back with tokens `c3ascend\" rel=\"noopener\"` and `grammarly _ primary
# purple"`. Written to portals.yml those become boards that 404 on every scan.


def test_a_token_never_swallows_trailing_html():
    from sources.ats_fingerprint import fingerprint_url

    hit = fingerprint_url('https://boards.greenhouse.io/c3ascend\\" rel=\\"noopener\\"')
    assert hit and hit["token"] == "c3ascend"
    assert hit["api"] == "https://boards-api.greenhouse.io/v1/boards/c3ascend/jobs"


def test_a_token_stops_at_whitespace():
    from sources.ats_fingerprint import fingerprint_url

    hit = fingerprint_url('https://boards.greenhouse.io/grammarly _ primary purple"')
    assert hit and hit["token"] == "grammarly"


def test_query_strings_and_trailing_slashes_are_not_part_of_the_token():
    from sources.ats_fingerprint import fingerprint_url

    assert fingerprint_url("https://job-boards.greenhouse.io/talkdesk2?x=1")["token"] == "talkdesk2"
    assert fingerprint_url("https://jobs.lever.co/acme/")["token"] == "acme"


def test_the_ats_own_paths_are_not_mistaken_for_a_company():
    """boards.greenhouse.io/embed/... is Greenhouse's own route, not an employer."""
    from sources.ats_fingerprint import fingerprint_url

    assert fingerprint_url("https://boards.greenhouse.io/embed/job_board?for=acme") is None


def test_ordinary_slugs_still_resolve():
    from sources.ats_fingerprint import fingerprint_url

    for url, ats, token in [
        ("https://boards.greenhouse.io/duolingo", "greenhouse", "duolingo"),
        ("https://jobs.ashbyhq.com/langfuse", "ashby", "langfuse"),
        ("https://acme.recruitee.com/careers", "recruitee", "acme"),
    ]:
        hit = fingerprint_url(url)
        assert hit and hit["ats_type"] == ats and hit["token"] == token


def test_scanning_many_urls_runs_them_together(monkeypatch):
    """219 careers pages sequentially at a 12s timeout is 40+ minutes."""
    import threading

    from sources import ats_fingerprint as fp

    urls = [f"https://co{i}.test/careers" for i in range(8)]

    # The barrier is the whole assertion: no scan may leave until every scan
    # has arrived, which can only happen if all eight really are in flight at
    # once. A serial implementation leaves the first one waiting by itself
    # until the timeout breaks it.
    #
    # That is a fact about the code rather than about how busy the runner is.
    # This test used to sleep 0.2s per scan and require the total to come in
    # under 80% of the serial cost — a bound only 0.32s clear of failure. A
    # loaded Windows runner took 1.44s against a 1.28s limit and failed a PR
    # that had not touched this file, the second such false alarm. The timeout
    # below is one-sided and ~1000x the room a healthy run needs, so runner
    # load cannot reach it; only genuinely serial work can.
    #
    # Sized to len(urls) because the pool is min(12, len(urls)) wide. Narrowing
    # the pool below eight is a deliberate change, and belongs here too.
    barrier = threading.Barrier(len(urls))
    ran_alone = threading.Event()

    def scan(url, **kw):
        try:
            barrier.wait(timeout=10)
        except threading.BrokenBarrierError:
            ran_alone.set()
        return {"url": url, "ok": False, "hit": None}

    monkeypatch.setattr(fp, "scan_careers_url", scan)
    out = fp.propose_from_urls(urls)

    assert not ran_alone.is_set(), "scans did not overlap: they ran one at a time"
    assert len(out) == len(urls), "a URL was dropped"


def test_proposal_order_matches_the_input(monkeypatch):
    """Callers line proposals up with what they asked for."""
    from sources import ats_fingerprint as fp

    monkeypatch.setattr(fp, "scan_careers_url",
                        lambda url, **kw: {"url": url, "ok": False, "hit": None})
    urls = [f"https://co{i}.test/careers" for i in range(5)]
    assert [p["url"] for p in fp.propose_from_urls(urls)] == urls
