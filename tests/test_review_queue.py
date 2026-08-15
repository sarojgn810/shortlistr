"""The review queue — jobs ordered by evidence, one at a time.

The pile this replaces was 385 evaluated jobs in a single bucket, 47% of them
sharing the top score band. The queue only promises what it can actually keep:
an ordering you can trust, over the jobs that have evidence behind them.

The important rule is that evidence-derived scores and the older model-guessed
numbers never share a sort. They are not the same measurement — the honest
scores top out at 4.6 while the guessed ones reach 5.0, so mixing them ranks
the *least* reliable jobs highest.
"""

from __future__ import annotations

import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))


@pytest.fixture
def store(monkeypatch, tmp_path):
    import config

    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    import store.db as db

    monkeypatch.setattr(db, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(db, "DB_PATH", os.path.join(str(tmp_path), "shortlistr.db"))
    db.init_db()
    return db


def add_job(db, job_id, *, company, title, score, met, total, source="evidence",
            status="evaluated"):
    must = [{"req": f"r{i}", "met": i < met, "evidence": "cv" if i < met else ""}
            for i in range(total)]
    payload = {
        "schema_version": "v1", "score": score, "legitimacy": "likely",
        "company": company, "role": title, "blocks": {"A": "fit"},
        "must_haves": must, "score_source": source,
    }
    with db.db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO jobs (id,url,source,company,title,jd_text) VALUES (?,?,?,?,?,?)",
            (job_id, f"https://x.test/{job_id}", "test", company, title, "x" * 400),
        )
        conn.execute("INSERT INTO pipeline (job_id, status) VALUES (?,?)", (job_id, status))
        conn.execute(
            "INSERT INTO eval_results (job_id, schema_version, score, legitimacy, result_json) "
            "VALUES (?,?,?,?,?)", (job_id, "v1", score, "likely", json.dumps(payload)))
        conn.execute(
            "INSERT INTO applications (job_id, company, role, score, status) VALUES (?,?,?,?,?)",
            (job_id, company, title, score, "evaluated"))


def test_orders_best_first(store):
    from review.queue import fetch_queue

    add_job(store, "a", company="Acme", title="SRE", score=3.3, met=3, total=4)
    add_job(store, "b", company="Best", title="SRE", score=4.6, met=11, total=11)
    add_job(store, "c", company="Mid", title="SRE", score=4.0, met=5, total=6)

    items = fetch_queue()["items"]

    assert [i["job_id"] for i in items] == ["b", "c", "a"]


def test_excludes_legacy_scores_from_the_ordering(store):
    from review.queue import fetch_queue

    add_job(store, "honest", company="Real", title="SRE", score=4.6, met=11, total=11)
    add_job(store, "guessed", company="Stale", title="SRE", score=5.0, met=0, total=0,
            source="model")

    result = fetch_queue()

    # The guessed 5.0 would otherwise outrank every honest score, since those
    # top out at 4.6 — the queue would lead with its least reliable entry.
    assert [i["job_id"] for i in result["items"]] == ["honest"]
    assert result["pending_reevaluation"] == 1


def test_shows_the_evidence_behind_the_score(store):
    from review.queue import fetch_queue

    add_job(store, "a", company="Acme", title="SRE", score=3.3, met=3, total=5)

    item = fetch_queue()["items"][0]

    # "You meet 3 of 5, these two are missing" is the part the user can act on.
    assert item["met"] == 3
    assert item["total"] == 5
    assert len(item["unmet"]) == 2


def test_only_offers_jobs_awaiting_a_decision(store):
    from review.queue import fetch_queue

    add_job(store, "waiting", company="A", title="SRE", score=4.4, met=6, total=6)
    add_job(store, "done", company="B", title="SRE", score=4.4, met=6, total=6,
            status="approved")
    add_job(store, "gone", company="C", title="SRE", score=4.4, met=6, total=6,
            status="skipped")

    ids = [i["job_id"] for i in fetch_queue()["items"]]

    assert ids == ["waiting"]


def test_respects_a_limit(store):
    from review.queue import fetch_queue

    for i in range(10):
        add_job(store, f"j{i}", company=f"C{i}", title="SRE", score=4.0, met=5, total=6)

    assert len(fetch_queue(limit=3)["items"]) == 3


def test_reports_an_empty_queue_without_failing(store):
    from review.queue import fetch_queue

    result = fetch_queue()

    assert result["items"] == []
    assert result["pending_reevaluation"] == 0
