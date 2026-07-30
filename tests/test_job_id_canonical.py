"""Every job's canonical id must be the 16-hex URL hash, regardless of source.

Regression guard for the bug where aggregator scrapers (RemoteOK numeric id,
WeWorkRemotely guid=URL, NoDesk/Jobspresso href) leaked a non-hex id into the DB
primary key, which then failed the API's `validate_job_id` and made the job
non-actionable (400/404 on view/evaluate/approve).
"""

from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "automation"))

from models.job import JobRecord, job_id_from_url  # noqa: E402

_HEX16 = re.compile(r"^[a-f0-9]{16}$")


def test_url_only_record_gets_hex_id():
    rec = JobRecord(url="https://boards.greenhouse.io/acme/jobs/123", source="Greenhouse",
                    company="Acme", title="SRE")
    assert _HEX16.match(rec.job_id)


def test_source_provided_url_id_is_overridden():
    # WeWorkRemotely sets job_id = RSS guid = the URL.
    url = "https://weworkremotely.com/remote-jobs/acme-sre"
    rec = JobRecord(url=url, source="WeWorkRemotely", company="Acme", title="SRE",
                    job_id=url)
    assert _HEX16.match(rec.job_id)
    assert rec.job_id == job_id_from_url(url)
    # original is preserved for traceability
    assert rec.metadata.get("source_job_id") == url


def test_source_provided_numeric_id_is_overridden():
    # RemoteOK / Remotive set job_id = numeric source id.
    rec = JobRecord(url="https://remoteok.com/remote-jobs/1134216", source="RemoteOK",
                    company="X", title="DevOps", job_id="1134216")
    assert _HEX16.match(rec.job_id)
    assert rec.metadata.get("source_job_id") == "1134216"


def test_from_dict_normalizes_id():
    rec = JobRecord.from_dict({
        "url": "https://example.com/jobs/abc",
        "source": "NoDesk",
        "company": "Y",
        "title": "Platform Engineer",
        "job_id": "/jobs/abc",  # href
    })
    assert _HEX16.match(rec.job_id)


def test_same_url_yields_same_id():
    u = "https://boards.lever.co/acme/abc-def?utm=x"
    a = JobRecord(url=u, source="Lever", company="A", title="T")
    b = JobRecord(url=u.split("?")[0], source="Lever", company="A", title="T", job_id="999")
    assert a.job_id == b.job_id  # query string ignored, source id ignored
