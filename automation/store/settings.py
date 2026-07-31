"""User settings — scan schedule, CV template, onboarding state."""

from __future__ import annotations

import json
import os
from typing import Any

from store import db as store

DEFAULT_AUTOMATION: dict[str, Any] = {
    "scan_enabled": True,
    "scan_interval_hours": 24,
    "auto_evaluate": True,
    "auto_evaluate_min_score": 4.0,
    "auto_approve_score": 0,
    "last_scan_at": None,
    "last_scan_jobs": 0,
    "onboarding_complete": False,
}

DEFAULT_CV: dict[str, Any] = {
    "template_id": "ats-single",
    "last_generated_tex": None,
    "last_generated_pdf": None,
    "ats_score": 0,
    # "uploaded" = send the user's original uploaded resume.pdf as-is;
    # "generated" = send a tailored template PDF (per-job when available).
    "resume_source": "uploaded",
    # "auto" | 1 | 2 — how many pages the generated PDF must hold to. The fit
    # search picks a density to satisfy it; see cv/latex_builder.fit_to_pages.
    "page_target": "auto",
    "last_page_count": 0,
    "last_density": None,
}


def _get_json(tenant_id: str, key: str, default: dict) -> dict:
    store.init_db()
    with store.db() as conn:
        row = conn.execute(
            "SELECT value_json FROM user_settings WHERE tenant_id = ? AND key = ?",
            (tenant_id, key),
        ).fetchone()
    if not row:
        return dict(default)
    try:
        data = json.loads(row["value_json"] or "{}")
        out = dict(default)
        out.update(data if isinstance(data, dict) else {})
        return out
    except json.JSONDecodeError:
        return dict(default)


def _set_json(tenant_id: str, key: str, data: dict) -> dict:
    store.init_db()
    with store.db() as conn:
        conn.execute(
            """
            INSERT INTO user_settings (tenant_id, key, value_json, updated_at)
            VALUES (?, ?, ?, datetime('now'))
            ON CONFLICT(tenant_id, key) DO UPDATE SET
                value_json = excluded.value_json,
                updated_at = datetime('now')
            """,
            (tenant_id, key, json.dumps(data)),
        )
    return data


def get_automation_settings(tenant_id: str = "default") -> dict[str, Any]:
    return _get_json(tenant_id, "automation", DEFAULT_AUTOMATION)


def set_automation_settings(updates: dict[str, Any], tenant_id: str = "default") -> dict[str, Any]:
    current = get_automation_settings(tenant_id)
    current.update(updates)
    return _set_json(tenant_id, "automation", current)


def onboarding_essentials_gaps() -> list[str]:
    """What is still missing for a usable, post-setup home screen.

    File existence alone is not enough — ``make start`` seeds a placeholder
    ``cv.md``, and a blank ``profile.yml`` is not a finished setup. The Today
    page used to key only off the sticky ``onboarding_complete`` flag, which
    is set solely by the wizard's Done step; users who finish via Profile / CV
    upload never flip it and keep seeing "Continue Setup".
    """
    from cv.placeholder import is_placeholder_cv
    from paths import CV_PATH, PROFILE_PATH

    gaps: list[str] = []

    profile_ok = False
    if os.path.isfile(PROFILE_PATH):
        try:
            from profile_store import get_profile_for_ui

            profile = get_profile_for_ui()
            name = (profile.get("name") or "").strip()
            email = (profile.get("email") or "").strip()
            titles = profile.get("target_titles") or []
            profile_ok = bool(name and email and titles)
        except Exception:
            profile_ok = False
    if not profile_ok:
        gaps.append("profile (name, email, and at least one target title)")

    cv_ok = False
    if os.path.isfile(CV_PATH):
        try:
            md = open(CV_PATH, encoding="utf-8").read()
            cv_ok = not is_placeholder_cv(md)
        except OSError:
            cv_ok = False
    if not cv_ok:
        gaps.append("a real résumé (not the placeholder cv.md)")

    from config import DATA_DIR

    if not os.path.isfile(os.path.join(DATA_DIR, "shortlistr.db")):
        gaps.append("local database")

    return gaps


def effective_onboarding_complete(
    automation: dict[str, Any] | None = None,
    tenant_id: str = "default",
) -> tuple[bool, list[str]]:
    """Wizard flag OR essentials met. Returns (complete, remaining gaps)."""
    auto = automation if automation is not None else get_automation_settings(tenant_id)
    gaps = onboarding_essentials_gaps()
    if auto.get("onboarding_complete"):
        return True, []
    if not gaps:
        return True, []
    return False, gaps


def get_cv_settings(tenant_id: str = "default") -> dict[str, Any]:
    return _get_json(tenant_id, "cv", DEFAULT_CV)


def set_cv_settings(updates: dict[str, Any], tenant_id: str = "default") -> dict[str, Any]:
    current = get_cv_settings(tenant_id)
    current.update(updates)
    return _set_json(tenant_id, "cv", current)


def get_agent_settings(tenant_id: str = "default") -> dict[str, Any]:
    """Agent autonomy settings, incl. the autopilot allowlist of submit-class tools."""
    return _get_json(tenant_id, "agent", {"autopilot_tools": []})


def set_agent_settings(updates: dict[str, Any], tenant_id: str = "default") -> dict[str, Any]:
    current = get_agent_settings(tenant_id)
    current.update(updates)
    return _set_json(tenant_id, "agent", current)


def get_prep_drafts(tenant_id: str = "default") -> dict[str, str]:
    raw = _get_json(tenant_id, "prep_drafts", {})
    return {str(k): str(v) for k, v in raw.items() if v}


def set_prep_cover_draft(job_id: str, body: str, tenant_id: str = "default") -> None:
    drafts = get_prep_drafts(tenant_id)
    drafts[job_id] = body.strip()
    _set_json(tenant_id, "prep_drafts", drafts)


def get_prep_reach_out(tenant_id: str = "default") -> dict[str, Any]:
    """Per-job Reach out drafts: {job_id: {contacts: [...], outreach_draft: str}}."""
    raw = _get_json(tenant_id, "prep_reach_out", {})
    if not isinstance(raw, dict):
        return {}
    out: dict[str, Any] = {}
    for k, v in raw.items():
        if isinstance(v, dict):
            out[str(k)] = v
    return out


def set_prep_reach_out_entry(
    job_id: str,
    *,
    contacts: list | None = None,
    outreach_draft: str | None = None,
    tenant_id: str = "default",
) -> dict[str, Any]:
    data = get_prep_reach_out(tenant_id)
    entry = dict(data.get(job_id) or {})
    if contacts is not None:
        entry["contacts"] = list(contacts)
    if outreach_draft is not None:
        entry["outreach_draft"] = outreach_draft.strip()
    data[job_id] = entry
    _set_json(tenant_id, "prep_reach_out", data)
    return entry
