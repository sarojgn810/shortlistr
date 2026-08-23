"""shortlistr test suite (ported from test-all.mjs)."""

from __future__ import annotations

import os
import re
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUTOMATION = os.path.join(ROOT, "automation")
# At import, not inside a test: conftest's autouse fixture imports `config`
# first, and the repo-root `config/` directory shadows automation/config.py
# unless automation/ is already on the path.
sys.path.insert(0, AUTOMATION)


def _run(cmd: list[str], cwd: str | None = None) -> tuple[int, str]:
    try:
        out = subprocess.run(
            cmd, cwd=cwd or ROOT, capture_output=True, text=True, timeout=30
        )
        return out.returncode, (out.stdout or "") + (out.stderr or "")
    except Exception as e:
        return 1, str(e)


def test_python_files_compile():
    import compileall
    assert compileall.compile_dir(AUTOMATION, quiet=1)


@pytest.mark.parametrize(
    "script",
    [
        "automation/cli.py",
        "automation/doctor.py",
        "automation/generate_pdf.py",
        "automation/check_liveness.py",
        "automation/tracker_tools/verify_pipeline.py",
        "automation/tracker_tools/normalize_statuses.py",
        "automation/tracker_tools/dedup_tracker.py",
        "automation/tracker_tools/merge_tracker.py",
        "automation/processors/scan_portals.py",
        "automation/processors/search_discovery.py",
        "automation/scrapers/ats_url_resolver.py",
    ],
)
def test_script_syntax(script: str):
    path = os.path.join(ROOT, script)
    rc, _ = _run([sys.executable, "-m", "py_compile", path])
    assert rc == 0


def test_verify_pipeline_runs():
    rc, _ = _run([sys.executable, "-m", "automation.cli", "verify"], cwd=ROOT)
    assert rc == 0


def test_normalize_statuses_runs():
    rc, _ = _run([sys.executable, "-m", "automation.cli", "normalize"], cwd=ROOT)
    assert rc == 0


def test_dedup_tracker_runs():
    rc, _ = _run([sys.executable, "-m", "automation.cli", "dedup"], cwd=ROOT)
    assert rc == 0


def test_merge_tracker_runs():
    rc, _ = _run([sys.executable, "-m", "automation.cli", "merge"], cwd=ROOT)
    assert rc == 0


def test_liveness_classification():
    sys.path.insert(0, AUTOMATION)
    from tracker_tools.liveness import classify_liveness

    expired = classify_liveness(
        final_url="https://example.com/jobs/closed-role",
        body_text="Company Careers\nApply\nThe job you are looking for is no longer open.",
        apply_controls=[],
    )
    assert expired["result"] == "expired"

    active = classify_liveness(
        final_url="https://example.workday.com/job/123",
        body_text=(
            "663 JOBS FOUND\nSenior AI Engineer\n"
            "Join our applied AI team to ship production systems."
        ),
        apply_controls=["Apply for this Job"],
    )
    assert active["result"] == "active"


@pytest.mark.parametrize(
    "path",
    [
        "AGENTS.md", "VERSION", "docs/ARCHITECTURE.md",
        "modes/_shared.md", "modes/_profile.template.md",
        "modes/evaluate.md", "modes/generate-cv.md", "modes/scan.md",
        "templates/states.yml", "templates/cv-template.html",
        "templates/applications.example.md", "skills/shortlistr/SKILL.md",
    ],
)
def test_system_files_exist(path: str):
    assert os.path.exists(os.path.join(ROOT, path))


@pytest.mark.parametrize(
    "path",
    ["config/profile.yml", "modes/_profile.md", "portals.yml"],
)
def test_user_files_gitignored(path: str):
    rc, out = _run(["git", "ls-files", path], cwd=ROOT)
    assert rc == 0
    assert out.strip() == ""


def test_no_personal_data_leaks():
    # Prior-owner identity must never leak. AI-tool strings (Claude Code,
    # CLAUDE.md, .claude/skills) are intentionally allowed: the project now ships
    # its own CLAUDE.md dev docs.
    leak_patterns = [
        "Santiago", "santifer.io", "career-ops", "career_ops", "Cursor IDE",
    ]
    extensions = ("md", "yml", "html", "py", "sh")
    # test_shortlistr.py defines the patterns above, so it self-matches — exempt it.
    allowed = {"LICENSE", "SECURITY.md", "README.md", "tests/test_shortlistr.py"}
    pathspecs = [f"*.{e}" for e in extensions]
    for pattern in leak_patterns:
        rc, out = _run(["git", "grep", "-n", pattern, "--", *pathspecs], cwd=ROOT)
        if rc != 0 or not out.strip():
            continue
        for line in out.strip().split("\n"):
            file = line.split(":")[0]
            if any(a in file for a in allowed):
                continue
            pytest.fail(f'Possible leak in {file}: "{pattern}"')


def test_no_absolute_paths_in_code():
    rc, out = _run(
        ["git", "grep", "-n", "/Users/", "--", "*.py", "*.sh", "*.md", "*.yml"],
        cwd=ROOT,
    )
    if rc == 0 and out.strip():
        filtered = [
            l for l in out.strip().split("\n")
            if not any(x in l for x in ("README.md", "LICENSE", "AGENTS.md", "tests/"))
        ]
        assert not filtered, f"Absolute paths found:\n" + "\n".join(filtered)


@pytest.mark.parametrize(
    "mode",
    [
        "_shared.md", "_profile.template.md", "evaluate.md", "generate-cv.md",
        "scan.md", "apply.md", "evaluate-full.md", "inbox.md", "tracker.md",
    ],
)
def test_mode_files_exist(mode: str):
    assert os.path.exists(os.path.join(ROOT, "modes", mode))


def test_shared_references_profile():
    shared = open(os.path.join(ROOT, "modes", "_shared.md"), encoding="utf-8").read()
    assert "_profile.md" in shared


@pytest.mark.parametrize(
    "section",
    [
        "Data Contract", "Ethical Use", "Offer Verification",
        "Canonical States", "TSV Format", "First Run", "Onboarding",
    ],
)
def test_agents_sections(section: str):
    agents = open(os.path.join(ROOT, "AGENTS.md"), encoding="utf-8").read()
    assert section in agents


def test_version_semver():
    version = open(os.path.join(ROOT, "VERSION"), encoding="utf-8").read().strip()
    assert re.match(r"^\d+\.\d+\.\d+$", version)


def test_no_node_mjs_in_repo():
    for name in os.listdir(ROOT):
        if name.endswith(".mjs"):
            pytest.fail(f"Node script still present: {name}")
    assert not os.path.exists(os.path.join(ROOT, "package.json"))


def _seed_store_for_verify(monkeypatch, tmp_path):
    """A real initialized store at <root>/data/shortlistr.db, with the module
    attributes _verify_sqlite reads pinned at it.

    SHORTLISTR_ROOT and DB_PATH are both snapshotted at import, so setting an
    env var here would leave the check pointing at the live database.
    """
    import store.db as db_mod
    from tracker_tools import verify_pipeline

    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr(db_mod, "DB_PATH", str(data / "shortlistr.db"))
    monkeypatch.setattr(db_mod, "LEGACY_DB_PATH", str(data / "autojob.db"))
    monkeypatch.setattr(verify_pipeline, "SHORTLISTR_ROOT", str(tmp_path))
    db_mod.init_db()
    return db_mod, verify_pipeline


def test_verify_sqlite_counts_receipts_without_warning(monkeypatch, tmp_path, capsys):
    """The receipts count and the status check ran after the `with store.db()`
    block had closed the connection, so both raised and were swallowed as a
    "SQLite check skipped" warning. `make verify` never validated either."""
    db_mod, verify_pipeline = _seed_store_for_verify(monkeypatch, tmp_path)
    with db_mod.db() as conn:
        conn.execute(
            "INSERT INTO jobs (id, url, source, title) "
            "VALUES ('j1', 'u1', 'test', 'SRE')"
        )
        conn.execute("INSERT INTO pipeline (job_id, status) VALUES ('j1', 'submitted')")
        conn.execute(
            "INSERT INTO application_receipts (job_id, channel) VALUES ('j1', 'email')"
        )

    errors: list[str] = []
    warnings: list[str] = []
    verify_pipeline._verify_sqlite(errors, warnings)
    out = capsys.readouterr().out

    assert warnings == []
    assert errors == []
    assert "SQLite receipts: 1" in out


def test_verify_sqlite_flags_invalid_pipeline_status(monkeypatch, tmp_path):
    """pipeline.status has no CHECK constraint, so this check is the only thing
    standing between a typo'd status and a job stuck outside the state machine."""
    db_mod, verify_pipeline = _seed_store_for_verify(monkeypatch, tmp_path)
    with db_mod.db() as conn:
        conn.execute(
            "INSERT INTO jobs (id, url, source, title) "
            "VALUES ('j1', 'u1', 'test', 'SRE')"
        )
        conn.execute("INSERT INTO pipeline (job_id, status) VALUES ('j1', 'aproved')")

    errors: list[str] = []
    warnings: list[str] = []
    verify_pipeline._verify_sqlite(errors, warnings)

    assert warnings == []
    assert any("invalid status" in e for e in errors), errors
