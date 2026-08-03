"""Approving a role has to leave it with prep materials.

Six of eight approved roles had a prep guide; GoDaddy and Entrupy had none. The
chain existed only in the browser: `mark_approved` is a two-line status write,
and the dashboard called `generatePrep` immediately afterwards. So an approval
from the chat agent, a script or curl produced no materials at all, and in the
Pipeline drawer both calls shared one try/except — a prep failure reported
"Could not approve" for an approval that had already landed, which is how a role
ends up approved and empty.

Now the API schedules prep itself and the generator is idempotent, so running
from both ends costs one generation, not two.
"""

from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))


# ── idempotence ──────────────────────────────────────────────────────────────

def test_ensure_skips_generation_when_prep_already_exists(monkeypatch):
    """The expensive path must not run twice for one approval."""
    from api import prep_bundle

    calls = []
    monkeypatch.setattr(prep_bundle, "prep_exists", lambda jid: True)
    monkeypatch.setattr(
        prep_bundle, "get_prep_bundle",
        lambda jid, generate=False: calls.append(generate) or {"job_id": jid},
    )

    prep_bundle.ensure_prep_bundle("a" * 16)
    assert calls == [False], "should have read existing prep, not regenerated it"


def test_ensure_generates_when_prep_is_missing(monkeypatch):
    from api import prep_bundle

    calls = []
    monkeypatch.setattr(prep_bundle, "prep_exists", lambda jid: False)
    monkeypatch.setattr(
        prep_bundle, "get_prep_bundle",
        lambda jid, generate=False: calls.append(generate) or {"job_id": jid},
    )

    prep_bundle.ensure_prep_bundle("b" * 16)
    assert calls == [True]


def test_ensure_rechecks_under_the_lock(monkeypatch):
    """Two approvals racing: the loser must not generate a second time.

    The first check happens before the lock is taken, so the other caller can
    finish in between. Without the re-check inside the lock we would pay for a
    second LLM call and race on one output file.
    """
    from api import prep_bundle

    seen = {"n": 0}

    def exists(jid):
        # missing on the first look, present by the time the lock is held
        seen["n"] += 1
        return seen["n"] > 1

    calls = []
    monkeypatch.setattr(prep_bundle, "prep_exists", exists)
    monkeypatch.setattr(
        prep_bundle, "get_prep_bundle",
        lambda jid, generate=False: calls.append(generate) or {"job_id": jid},
    )

    prep_bundle.ensure_prep_bundle("c" * 16)
    assert calls == [False], "re-check under the lock should have prevented generation"


def test_ensure_is_not_defeated_by_a_missing_lock_primitive(monkeypatch):
    """Windows without msvcrt, or any platform filelock can't serve, still preps.

    filelock degrades to telling the caller it holds the lock. Refusing to
    prepare anything would be far worse than a rare duplicate.
    """
    from api import prep_bundle
    from store import filelock

    monkeypatch.setattr(filelock, "acquire", lambda fh, blocking=True: True)
    monkeypatch.setattr(filelock, "release", lambda fh: None)
    monkeypatch.setattr(prep_bundle, "prep_exists", lambda jid: False)

    calls = []
    monkeypatch.setattr(
        prep_bundle, "get_prep_bundle",
        lambda jid, generate=False: calls.append(generate) or {"job_id": jid},
    )
    prep_bundle.ensure_prep_bundle("d" * 16)
    assert calls == [True]


# ── the approve endpoint schedules it ────────────────────────────────────────

def test_approving_schedules_prep():
    """Approval from any client — not just the dashboard — queues generation."""
    import inspect

    from api import main as api_main

    src = inspect.getsource(api_main)
    approve = src[src.index('@app.post("/jobs/{job_id}/pipeline-status")'):]
    approve = approve[: approve.index("@app.get(")]

    assert "mark_approved" in approve
    assert "background.add_task(_prep_after_approve" in approve, (
        "approving must schedule prep, or non-browser approvals leave a role empty"
    )


def test_prep_after_approve_swallows_failures():
    """A prep failure must never turn a successful approval into an error."""
    from api import main as api_main
    import inspect

    src = inspect.getsource(api_main)
    fn = src[src.index("def _prep_after_approve"):]
    fn = fn[: fn.index("@app.post")]
    assert "except Exception" in fn
    assert "logging.getLogger" in fn, "uses a locally-scoped logger, not the scheduler's"


# ── the dashboard keeps approval and prep separate ───────────────────────────

@pytest.mark.parametrize("page", ["pipeline", "inbox"])
def test_dashboard_reports_prep_failure_without_claiming_approval_failed(page):
    path = os.path.join(ROOT, "dashboard", "app", page, "page.tsx")
    src = open(path, encoding="utf-8").read()
    start = src.index("const handleApprove")
    body = src[start: start + 2000]

    assert "api.ensurePrep" in body, "approve should ensure, not force-regenerate"
    assert "Approved, but" in body, (
        "a prep failure must say the approval landed — reporting "
        "'Could not approve' is what left roles approved and empty"
    )


def test_approve_does_not_discard_an_edited_cover_letter():
    """ensurePrep, not generatePrep: re-approving must not overwrite a draft."""
    for page in ("pipeline", "inbox"):
        path = os.path.join(ROOT, "dashboard", "app", page, "page.tsx")
        src = open(path, encoding="utf-8").read()
        start = src.index("const handleApprove")
        body = src[start: start + 2000]
        assert "api.generatePrep" not in body, f"{page} still force-regenerates on approve"


# ── the lock must not litter the user's own material ─────────────────────────

def test_lock_file_is_not_written_into_interview_prep(monkeypatch, tmp_path):
    """interview-prep/ is content the user reads, syncs and backs up.

    The first version put `.<job_id>.lock` next to the guides, which left stray
    dotfiles in that directory — including from this very test file.
    """
    from api import prep_bundle

    prep_dir = tmp_path / "interview-prep"
    prep_dir.mkdir()
    monkeypatch.setattr(prep_bundle, "PREP_DIR", str(prep_dir))
    monkeypatch.setattr(prep_bundle, "prep_exists", lambda jid: False)
    monkeypatch.setattr(
        prep_bundle, "get_prep_bundle", lambda jid, generate=False: {"job_id": jid})

    prep_bundle.ensure_prep_bundle("e" * 16)

    strays = [p.name for p in prep_dir.iterdir() if p.name.endswith(".lock")]
    assert strays == [], f"lock files leaked into the prep directory: {strays}"
