"""Job inventory lifecycle: dedup on re-ingest, two-strike archiving, and the
purge guards that stop referral history being orphaned."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "automation"))

import pytest

from jobs import liveness_sweep as sweep_mod
from models.job import JobRecord
from store import db as store


def _job(url, **kw):
    return JobRecord(
        url=url,
        source=kw.pop("source", "Greenhouse"),
        company=kw.pop("company", "Acme"),
        title=kw.pop("title", "Engineer"),
        jd_text=kw.pop("jd_text", "Java Spring Boot Kafka " * 20),
        **kw,
    )


def _count(sql="SELECT COUNT(*) c FROM jobs", params=()):
    with store.db() as conn:
        return int(conn.execute(sql, params).fetchone()["c"])


# ── dedup ────────────────────────────────────────────────────────────────────
def test_reingest_updates_in_place_no_duplicates():
    jobs = [_job("https://x.test/a"), _job("https://x.test/b")]
    assert store.upsert_jobs(jobs) == 2
    assert _count() == 2

    # Same URLs, refreshed content — must update, never insert.
    again = [_job("https://x.test/a", title="Senior Engineer"), _job("https://x.test/b")]
    store.upsert_jobs(again)
    assert _count() == 2
    with store.db() as conn:
        row = conn.execute("SELECT title FROM jobs WHERE url = 'https://x.test/a'").fetchone()
    assert row["title"] == "Senior Engineer"


def test_query_string_variants_are_the_same_job():
    store.upsert_jobs([_job("https://x.test/a")])
    store.upsert_jobs([_job("https://x.test/a?utm_source=rss")])
    assert _count() == 1  # job_id is sha256 of the URL without its query


def test_batch_pipeline_add_is_idempotent():
    store.upsert_jobs([_job("https://x.test/a")])
    jid = store.job_id_from_url("https://x.test/a")
    store.add_jobs_to_pipeline([jid])
    store.add_jobs_to_pipeline([jid])
    assert _count("SELECT COUNT(*) c FROM pipeline") == 1


def test_upsert_never_resurrects_an_archived_job():
    """The lifecycle columns must be absent from the upsert, or a re-scrape
    would silently un-archive a closed posting."""
    store.upsert_jobs([_job("https://x.test/a")])
    jid = store.job_id_from_url("https://x.test/a")
    with store.db() as conn:
        conn.execute(
            "UPDATE jobs SET archived_at = datetime('now'), dead_strikes = 2 WHERE id = ?",
            (jid,),
        )
    store.upsert_jobs([_job("https://x.test/a")])
    with store.db() as conn:
        row = conn.execute(
            "SELECT archived_at, dead_strikes FROM jobs WHERE id = ?", (jid,)
        ).fetchone()
    assert row["archived_at"] is not None and row["dead_strikes"] == 2


# ── two-strike archiving ─────────────────────────────────────────────────────
@pytest.fixture
def one_job(monkeypatch):
    store.upsert_jobs([_job("https://x.test/dead")])
    return store.job_id_from_url("https://x.test/dead")


def _fake_verdict(result):
    return lambda url, **kw: {"result": result, "reason": "test"}


def _row(jid):
    with store.db() as conn:
        return conn.execute(
            "SELECT liveness, dead_strikes, archived_at FROM jobs WHERE id = ?", (jid,)
        ).fetchone()


def test_dead_once_is_not_archived(one_job, monkeypatch):
    monkeypatch.setattr(sweep_mod, "check_url_http", _fake_verdict("dead"))
    res = sweep_mod.sweep(limit=10)
    assert res["dead"] == 1 and res["archived"] == 0
    r = _row(one_job)
    assert r["dead_strikes"] == 1 and r["archived_at"] is None


def test_dead_twice_archives(one_job, monkeypatch):
    monkeypatch.setattr(sweep_mod, "check_url_http", _fake_verdict("dead"))
    sweep_mod.sweep(limit=10, recheck_after_hours=0)
    res = sweep_mod.sweep(limit=10, recheck_after_hours=0)
    assert res["archived"] == 1
    assert _row(one_job)["archived_at"] is not None


def test_live_verdict_resets_strikes(one_job, monkeypatch):
    monkeypatch.setattr(sweep_mod, "check_url_http", _fake_verdict("dead"))
    sweep_mod.sweep(limit=10, recheck_after_hours=0)
    monkeypatch.setattr(sweep_mod, "check_url_http", _fake_verdict("live"))
    sweep_mod.sweep(limit=10, recheck_after_hours=0)
    r = _row(one_job)
    assert r["dead_strikes"] == 0 and r["archived_at"] is None


def test_uncertain_never_increments_strikes(one_job, monkeypatch):
    """A 403 or a timeout says nothing about the posting."""
    monkeypatch.setattr(sweep_mod, "check_url_http", _fake_verdict("uncertain"))
    sweep_mod.sweep(limit=10, recheck_after_hours=0)
    sweep_mod.sweep(limit=10, recheck_after_hours=0)
    r = _row(one_job)
    assert r["dead_strikes"] == 0 and r["archived_at"] is None


def test_dry_run_writes_nothing(one_job, monkeypatch):
    monkeypatch.setattr(sweep_mod, "check_url_http", _fake_verdict("dead"))
    sweep_mod.sweep(limit=10, dry_run=True)
    r = _row(one_job)
    assert r["dead_strikes"] == 0 and r["liveness"] is None


def test_archived_jobs_are_not_rechecked(one_job, monkeypatch):
    monkeypatch.setattr(sweep_mod, "check_url_http", _fake_verdict("dead"))
    sweep_mod.sweep(limit=10, recheck_after_hours=0)
    sweep_mod.sweep(limit=10, recheck_after_hours=0)  # archived here
    res = sweep_mod.sweep(limit=10, recheck_after_hours=0)
    assert res["checked"] == 0


# ── purge guards ─────────────────────────────────────────────────────────────
def _archive(jid, days_ago):
    with store.db() as conn:
        conn.execute(
            "UPDATE jobs SET archived_at = datetime('now', ?) WHERE id = ?",
            (f"-{days_ago} days", jid),
        )


def test_purge_removes_only_old_unreferenced_jobs():
    store.upsert_jobs([_job("https://x.test/old"), _job("https://x.test/recent")])
    old = store.job_id_from_url("https://x.test/old")
    recent = store.job_id_from_url("https://x.test/recent")
    _archive(old, 40)
    _archive(recent, 3)

    res = sweep_mod.purge_archived(older_than_days=30)
    assert res["purged"] == 1
    assert _count("SELECT COUNT(*) c FROM jobs WHERE id = ?", (old,)) == 0
    assert _count("SELECT COUNT(*) c FROM jobs WHERE id = ?", (recent,)) == 1


def test_purge_spares_a_job_with_a_referral():
    """The referrals table lives in the platform DB now, but the guard still has
    to hold on whichever database the sweep runs against."""
    store.upsert_jobs([_job("https://x.test/referred")])
    jid = store.job_id_from_url("https://x.test/referred")
    _archive(jid, 90)
    with store.db() as conn:
        conn.execute(
            "INSERT INTO referrals (candidate_name, job_ref, referred_at, job_id) "
            "VALUES ('Asha M', 'Engineer @ Acme', date('now'), ?)", (jid,))

    assert sweep_mod.purge_archived(older_than_days=30)["purged"] == 0
    assert _count("SELECT COUNT(*) c FROM jobs WHERE id = ?", (jid,)) == 1


def test_purge_spares_a_job_with_an_application():
    store.upsert_jobs([_job("https://x.test/applied")])
    jid = store.job_id_from_url("https://x.test/applied")
    _archive(jid, 90)
    with store.db() as conn:
        conn.execute(
            "INSERT INTO applications (job_id, company, role, status) VALUES (?, ?, ?, ?)",
            (jid, "Acme", "Engineer", "applied"),
        )
    assert sweep_mod.purge_archived(older_than_days=30)["purged"] == 0


def test_purge_spares_a_job_that_moved_past_pending():
    store.upsert_jobs([_job("https://x.test/evaluated")])
    jid = store.job_id_from_url("https://x.test/evaluated")
    store.add_jobs_to_pipeline([jid])
    with store.db() as conn:
        conn.execute("UPDATE pipeline SET status = 'evaluated' WHERE job_id = ?", (jid,))
    _archive(jid, 90)
    assert sweep_mod.purge_archived(older_than_days=30)["purged"] == 0


def test_purge_dry_run_deletes_nothing():
    store.upsert_jobs([_job("https://x.test/old")])
    jid = store.job_id_from_url("https://x.test/old")
    _archive(jid, 90)
    assert sweep_mod.purge_archived(older_than_days=30, dry_run=True)["purged"] == 1
    assert _count("SELECT COUNT(*) c FROM jobs WHERE id = ?", (jid,)) == 1


def test_purged_job_takes_its_pending_pipeline_row(one_job=None):
    store.upsert_jobs([_job("https://x.test/old")])
    jid = store.job_id_from_url("https://x.test/old")
    store.add_jobs_to_pipeline([jid])
    _archive(jid, 90)
    sweep_mod.purge_archived(older_than_days=30)
    assert _count("SELECT COUNT(*) c FROM pipeline WHERE job_id = ?", (jid,)) == 0


# ── archived jobs are invisible to candidates ────────────────────────────────
def test_archived_jobs_do_not_reach_candidate_matching():
    from store.queries import fetch_candidate_jobs

    store.upsert_jobs([_job("https://x.test/live"), _job("https://x.test/gone")])
    _archive(store.job_id_from_url("https://x.test/gone"), 1)
    with store.db() as conn:
        rows = fetch_candidate_jobs(conn, limit=50)
    urls = {r["url"] for r in rows}
    assert "https://x.test/live" in urls and "https://x.test/gone" not in urls
