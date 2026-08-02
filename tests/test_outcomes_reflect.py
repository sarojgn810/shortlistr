"""O2 — reflect application outcomes into learnings (idempotent)."""

from __future__ import annotations

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))


def _isolate(monkeypatch):
    tmp = tempfile.mkdtemp()
    import config
    import store.db as db_mod

    monkeypatch.setattr(config, "DATA_DIR", tmp)
    monkeypatch.setattr(db_mod, "DATA_DIR", tmp)
    monkeypatch.setattr(db_mod, "DB_PATH", os.path.join(tmp, "shortlistr.db"))
    return tmp


def _seed(company, statuses, *, source="greenhouse", base=0):
    from models.job import JobRecord, job_id_from_url
    from store import db, status

    for i, stt in enumerate(statuses):
        url = f"https://boards.greenhouse.io/{company}/jobs/{base + i}"
        jid = job_id_from_url(url)
        db.upsert_job(JobRecord(url=url, source=source, company=company, title="SRE", job_id=jid))
        status.upsert_application(jid, company=company, role="SRE", score=4.0, status=stt)


def test_reflect_writes_and_is_idempotent(monkeypatch):
    _isolate(monkeypatch)
    from memory.store import search_learnings
    from outcomes.reflect import reflect
    from store import db

    db.init_db()
    _seed("GhostCo", ["applied", "applied", "applied", "applied"])
    _seed("GoodCo", ["responded", "interview", "applied", "applied"], base=100)

    keys = reflect()
    assert "outcome:company:GhostCo" in keys
    assert "outcome:company:GoodCo" in keys

    ghost = search_learnings("ghostco")
    assert len(ghost) == 1 and "deprioritize" in ghost[0]["insight"]
    good = search_learnings("goodco")
    assert len(good) == 1 and "prioritize" in good[0]["insight"]

    # idempotent: re-running recomputes, does not duplicate
    reflect()
    assert len(search_learnings("ghostco")) == 1


def test_reflect_ignores_small_samples(monkeypatch):
    _isolate(monkeypatch)
    from memory.store import search_learnings
    from outcomes.reflect import reflect
    from store import db

    db.init_db()
    _seed("Tiny", ["applied", "applied"])  # below MIN_SAMPLE
    reflect()
    assert search_learnings("tiny") == []
