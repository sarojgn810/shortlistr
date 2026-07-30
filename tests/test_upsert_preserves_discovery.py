"""Re-writing a job row must not erase what discovery already learned.

Regression: evaluating a discovered job upserts a placeholder row with
`source='eval'` and no location/salary/score. Because the upsert overwrote those
columns, an Apify-discovered MLOps role lost its salary and fit score, and its
source became 'eval' — which `queries.NO_EVAL_ARTIFACTS` filters out, so the job
disappeared from candidate matching after being evaluated.
"""

from __future__ import annotations

import os
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))


@pytest.fixture
def isolated_db(monkeypatch):
    tmp = tempfile.mkdtemp()
    import store.db as db_mod

    monkeypatch.setattr(db_mod, "DATA_DIR", tmp)
    monkeypatch.setattr(db_mod, "DB_PATH", os.path.join(tmp, "shortlistr.db"))
    return tmp


def _discovered():
    from models.job import JobRecord

    return JobRecord(
        url="https://in.linkedin.com/jobs/view/mlops-engineer-4438209671",
        source="LinkedIn",
        company="SourcingXPress",
        title="MLOps Engineer",
        location="Bengaluru",
        salary="₹ 30-45 LPA",
        fit_score=62,
        fit_reason="title match",
    )


def _row(job_id):
    from store import db as store

    with store.db() as conn:
        conn.row_factory = None
        return conn.execute(
            "SELECT source, location, salary, fit_score, fit_reason, jd_text"
            " FROM jobs WHERE id = ?",
            (job_id,),
        ).fetchone()


def test_evaluating_keeps_source_location_salary_and_score(isolated_db):
    from models.job import JobRecord
    from store import db as store

    job = _discovered()
    store.upsert_job(job)

    # What eval/service.py writes when attaching a result to a pasted URL.
    store.upsert_job(
        JobRecord(
            url=job.url,
            source="eval",
            company="SourcingXPress",
            title="MLOps Engineer",
            jd_text="Full JD text from the evaluation.",
            job_id=job.job_id,
        )
    )

    source, location, salary, fit_score, fit_reason, jd_text = _row(job.job_id)
    assert source == "LinkedIn"
    assert location == "Bengaluru"
    assert salary == "₹ 30-45 LPA"
    assert fit_score == 62
    assert fit_reason == "title match"
    # The one thing eval does add must still land.
    assert jd_text == "Full JD text from the evaluation."


def test_pasted_url_still_creates_an_eval_row(isolated_db):
    """The guard must not stop eval from recording a job we never discovered."""
    from models.job import JobRecord
    from store import db as store

    job = JobRecord(
        url="https://careers.example.com/roles/42",
        source="eval",
        company="Example",
        title="AIOps Engineer",
        jd_text="pasted",
    )
    store.upsert_job(job)
    assert _row(job.job_id)[0] == "eval"


def test_rescrape_without_salary_keeps_the_known_salary(isolated_db):
    from models.job import JobRecord
    from store import db as store

    job = _discovered()
    store.upsert_job(job)
    store.upsert_jobs([
        JobRecord(
            url=job.url,
            source="LinkedIn",
            company="SourcingXPress",
            title="MLOps Engineer",
            location="",
            salary="",
            job_id=job.job_id,
        )
    ])

    source, location, salary, fit_score, _, _ = _row(job.job_id)
    assert (source, location, salary, fit_score) == (
        "LinkedIn",
        "Bengaluru",
        "₹ 30-45 LPA",
        62,
    )


def test_rescrape_with_new_values_still_wins(isolated_db):
    from models.job import JobRecord
    from store import db as store

    job = _discovered()
    store.upsert_job(job)
    store.upsert_job(
        JobRecord(
            url=job.url,
            source="Naukri",
            company="SourcingXPress",
            title="Senior MLOps Engineer",
            location="Hyderabad",
            salary="₹ 40-55 LPA",
            fit_score=71,
            fit_reason="stronger match",
            job_id=job.job_id,
        )
    )

    source, location, salary, fit_score, fit_reason, _ = _row(job.job_id)
    assert (source, location, salary, fit_score, fit_reason) == (
        "Naukri",
        "Hyderabad",
        "₹ 40-55 LPA",
        71,
        "stronger match",
    )
