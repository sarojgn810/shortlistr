"""The "N pending review" badge must be a count, not a page length.

The badge used to be computed in the dashboard by filtering the job list for
`pipeline_status === "pending"`. That list is one page of at most 100 rows, so
the number really meant "pending jobs among the newest 100" — it read correctly
only while the user had fewer than a page of jobs, and stopped moving after that.
These tests pin the two server-side facts the badge now depends on:

  * `pipeline_status_counts(targeted=True)` counts every matching row, past any
    page boundary, behind the same relevance + fit gate as the inbox.
  * `fetch_jobs(status="approved")` returns approved rows directly, so the apply
    runner no longer has to find them inside a page of "evaluated" ones.
"""

from __future__ import annotations

import os
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))

PAGE_SIZE = 100  # dashboard/src/hooks/useJobs.ts


@pytest.fixture
def isolated_data_dir(monkeypatch):
    tmp = tempfile.mkdtemp()
    import config
    import store.db as db_mod

    monkeypatch.setattr(config, "DATA_DIR", tmp)
    monkeypatch.setattr(db_mod, "DATA_DIR", tmp)
    monkeypatch.setattr(db_mod, "DB_PATH", os.path.join(tmp, "shortlistr.db"))
    return tmp


def _seed(
    n: int,
    *,
    status: str = "pending",
    fit: int = 80,
    relevance: str = "relevant",
    prefix: str = "aaaa",
    added_at: str = "2026-01-01 00:00:00",
) -> list[str]:
    """n jobs in the pipeline at `status`, all passing the default view gate.

    Job ids must be 16 hex chars (`store.status.validate_job_id`), and `added_at`
    is set explicitly because the inbox orders by it — a page boundary is only
    meaningful if the test controls which rows land on which side of it.
    """
    import json

    from store import db as store

    store.init_db()
    ids = [f"{prefix}{i:012x}" for i in range(n)]
    with store.db() as conn:
        for jid in ids:
            conn.execute(
                "INSERT INTO jobs (id, url, source, company, title, location, "
                "fit_score, metadata_json) VALUES (?,?,?,?,?,?,?,?)",
                (
                    jid,
                    f"https://example.com/{jid}",
                    "greenhouse",
                    "Acme",
                    "Site Reliability Engineer",
                    "Bengaluru, India",
                    fit,
                    json.dumps({"discovery_relevance": relevance}),
                ),
            )
            conn.execute(
                "INSERT INTO pipeline (job_id, status, added_at) VALUES (?, ?, ?)",
                (jid, status, added_at),
            )
    return ids


def test_pending_count_survives_the_page_boundary(isolated_data_dir):
    """The bug: 150 jobs awaiting review, badge frozen at 100."""
    from api.jobs_api import fetch_jobs
    from store import db as store
    from store.status import pipeline_status_counts

    _seed(150)

    with store.db() as conn:
        page = fetch_jobs(conn, status="inbox", limit=PAGE_SIZE, relevance="relevant")
    assert len(page) == PAGE_SIZE, "one page is still capped — that part is correct"

    # What the dashboard used to do with that page.
    derived = sum(
        1 for j in page if not j.get("pipeline_status") or j["pipeline_status"] == "pending"
    )
    assert derived == PAGE_SIZE

    # What it does now.
    assert pipeline_status_counts(targeted=True)["pending"] == 150


def test_pending_count_applies_the_same_gate_as_the_inbox(isolated_data_dir):
    """A number next to a list has to count the rows in that list.

    Off-target jobs are hidden from the inbox, so counting them would send the
    user looking for jobs no view will show them.

    Low-fit jobs are a different matter and this test used to have it wrong. The
    inbox deliberately does not hide them — api/jobs_api.py sets its fit filter
    to "" so a rescored keeper never vanishes from Discover on its own — while
    the count applied a fit floor. Discover showed 16 pending and Today said 15,
    and the one it dropped was a relevant job scoring 20.
    """
    from store.status import pipeline_status_counts

    _seed(5, prefix="aaaa")
    _seed(40, relevance="off_target", prefix="bbbb")
    _seed(30, fit=10, prefix="cccc")

    counts = pipeline_status_counts(targeted=True)
    assert counts["pending"] == 35, "off-target excluded, low-fit counted"
    # The raw breakdown is deliberately different: it answers "what is in the DB".
    assert pipeline_status_counts()["pending"] == 75


def test_pending_count_drops_when_a_job_is_decided(isolated_data_dir):
    """Approving or skipping has to move the badge, or reviewing feels broken."""
    from store.status import mark_approved, mark_skipped, pipeline_status_counts

    ids = _seed(3)
    assert pipeline_status_counts(targeted=True)["pending"] == 3

    mark_approved(ids[0])
    mark_skipped(ids[1])

    counts = pipeline_status_counts(targeted=True)
    assert counts["pending"] == 1
    assert counts["approved"] == 1
    assert counts["skipped"] == 1


def test_approved_queue_is_not_hidden_behind_a_page_of_evaluated(isolated_data_dir):
    """The apply runner's queue.

    It asked for "evaluated" (which spans evaluated/approved/submitted) and kept
    the approved rows. With more than a page of evaluated jobs, an approval could
    fall outside the page and the runner would report nothing to apply to.
    """
    from api.jobs_api import fetch_jobs
    from store import db as store

    # The approvals are older, so a newest-first page of evaluated rows buries them.
    approved_ids = _seed(
        2, status="approved", prefix="dddd", added_at="2026-01-01 00:00:00"
    )
    _seed(
        PAGE_SIZE + 20, status="evaluated", prefix="eeee", added_at="2026-06-01 00:00:00"
    )

    with store.db() as conn:
        evaluated_page = fetch_jobs(conn, status="evaluated", limit=PAGE_SIZE)
        approved = fetch_jobs(conn, status="approved", limit=PAGE_SIZE)

    found_by_filtering = [j for j in evaluated_page if j["pipeline_status"] == "approved"]
    assert found_by_filtering == [], "the old approach loses them"

    assert {j["id"] for j in approved} == set(approved_ids)
    assert all(j["pipeline_status"] == "approved" for j in approved)
