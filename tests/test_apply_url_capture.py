"""Keeping the employer's real application URL when a source hands one over.

LinkedIn postings dominate this pipeline and none of them could be filled: the
stored URL is a linkedin.com job view, and LinkedIn only reveals the employer's
actual apply link to signed-in visitors. Resolving it after the fact means
scraping behind a login, which is both against their terms and a good way to
get an account restricted.

It turned out not to be necessary. The Apify actor already returns `applyUrl`
and `applyType` on every record — the adapter was recording the *names* of the
fields it received in `raw_keys` and discarding the values. So the link was
arriving all along and being thrown away one line before it was needed.
"""

from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))


def linkedin_item(**over):
    item = {
        "id": "4443287455",
        "title": "Site Reliability Engineer",
        "companyName": "Okta",
        "location": "Bangalore, India",
        "description": "Run production Kubernetes." * 20,
        "url": "https://in.linkedin.com/jobs/view/sre-at-okta-4443287455",
        "applyUrl": "https://boards.greenhouse.io/okta/jobs/1234567",
        "applyType": "OFFSITE",
        "companyUrl": "https://www.linkedin.com/company/okta",
    }
    item.update(over)
    return item


def build(item, source="linkedin"):
    from sources.adapters.apify_adapter import _item_to_record

    return _item_to_record(item, source=source)


def test_keeps_the_employers_apply_url():
    rec = build(linkedin_item())

    assert rec is not None
    # Without this the job is unfillable forever: a linkedin.com/jobs/view URL
    # has no form on it, and the real one cannot be recovered later.
    assert rec.metadata["apply_url"] == "https://boards.greenhouse.io/okta/jobs/1234567"


def test_records_whether_the_application_is_off_site():
    offsite = build(linkedin_item())
    onsite = build(linkedin_item(applyType="ONSITE", applyUrl=""))

    # Easy Apply postings are handled on LinkedIn behind a login, so they can
    # never be auto-filled. Knowing which is which is worth storing.
    assert offsite.metadata["apply_type"] == "offsite"
    assert onsite.metadata["apply_type"] == "onsite"


def test_ignores_an_apply_url_that_just_points_back_to_linkedin():
    rec = build(linkedin_item(applyUrl="https://www.linkedin.com/jobs/view/4443287455"))

    # That is the page we already have. Storing it would claim a fillable
    # application exists where none does.
    assert not rec.metadata.get("apply_url")


@pytest.mark.parametrize("bad", ["", None, "not-a-url", "javascript:void(0)"])
def test_ignores_junk_apply_urls(bad):
    rec = build(linkedin_item(applyUrl=bad))

    assert not rec.metadata.get("apply_url")


def test_reads_the_other_spellings_sources_use():
    for key in ("applyUrl", "apply_url", "applicationUrl", "externalApplyUrl"):
        rec = build(linkedin_item(**{
            "applyUrl": None, key: "https://jobs.lever.co/acme/abc-123",
        }))
        assert rec.metadata.get("apply_url") == "https://jobs.lever.co/acme/abc-123", key


def test_a_source_without_an_apply_url_still_builds():
    item = linkedin_item()
    item.pop("applyUrl")
    item.pop("applyType")

    rec = build(item)

    assert rec is not None
    assert not rec.metadata.get("apply_url")
