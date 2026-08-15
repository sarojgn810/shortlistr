"""The paths that can reach a Submit click, and the ones that must not.

Submission is the only irreversible thing this tool does. These tests are less
about behaviour than about keeping the blast radius where it was put: filling a
form stays separate from sending it, and everything that sends goes through one
function that checks approval first.
"""

from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "automation"))
AUTOMATION = os.path.join(ROOT, "automation")


def read(path: str) -> str:
    with open(os.path.join(AUTOMATION, path), encoding="utf-8") as fh:
        return fh.read()


def test_filling_a_form_does_not_submit_by_default():
    from apply.ats_fill import fill_application_form
    import inspect

    params = inspect.signature(fill_application_form).parameters

    # Manual apply-assist and every existing caller must keep stopping short of
    # sending. Flipping this default would turn every fill into a submission.
    assert params["submit"].default is False


def test_job_level_assist_does_not_submit_by_default():
    from apply.ats_fill import apply_assist_for_job
    import inspect

    assert inspect.signature(apply_assist_for_job).parameters["submit"].default is False


def test_only_the_submit_module_asks_for_a_submit():
    """Grep, deliberately: this is about who is allowed to, not what happens."""
    callers = []
    for folder, _, files in os.walk(AUTOMATION):
        if "__pycache__" in folder:
            continue
        for name in files:
            if not name.endswith(".py"):
                continue
            # os.path.relpath returns "apply\submit.py" on Windows, which never
            # matched the POSIX spellings below — so the two files allowed to
            # request a submit were reported as violations and only Windows CI
            # noticed.
            rel = os.path.relpath(os.path.join(folder, name), AUTOMATION).replace(os.sep, "/")
            if rel in ("apply/submit.py", "apply/ats_fill.py"):
                continue
            body = read(rel)
            if re.search(r"submit\s*=\s*True", body):
                callers.append(rel)

    assert callers == [], f"submit=True passed outside apply/submit.py: {callers}"


def test_background_jobs_do_not_reach_the_submit_path():
    """Discovery, ingest and the liveness sweep must never send anything."""
    for module in ("orchestrator/discovery.py", "jobs/ingest.py", "jobs/liveness_sweep.py",
                   "scheduler/scan_scheduler.py"):
        path = os.path.join(AUTOMATION, module)
        if not os.path.exists(path):
            continue
        body = read(module)
        assert "apply.submit" not in body, f"{module} imports the submit path"
        assert "submit_application" not in body, f"{module} can submit"


def test_submission_requires_approval_not_merely_evaluation():
    body = read("apply/submit.py")

    # "evaluated" means the machine formed an opinion and nobody agreed with it.
    # Accepting it here would quietly remove the human from the loop.
    assert 'status != "approved"' in body


def test_worker_routes_auto_apply_through_the_guarded_entry_point():
    body = read("workers/discovery_worker.py")

    assert 'task_type == "auto_apply"' in body
    # Not submit_application directly — run_scheduled_submission is what checks
    # the undo window and re-checks preconditions at send time.
    assert "run_scheduled_submission" in body
    assert "submit_application" not in body


def test_the_registry_still_classes_applying_as_submit_side_effect():
    from agent.registry import get_tool, SUBMIT

    # Whatever else changes, an agent asking to apply must stay gated behind the
    # permission check rather than becoming an ordinary write.
    assert get_tool("shortlistr.apply_assist").side_effect == SUBMIT
