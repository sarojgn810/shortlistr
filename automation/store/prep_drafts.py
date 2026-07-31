"""Saved prep drafts (cover letters + Reach out) per job."""

from __future__ import annotations

from typing import Any

from store.settings import (
    get_prep_drafts,
    get_prep_reach_out,
    set_prep_cover_draft,
    set_prep_reach_out_entry,
)


def get_cover_letter_draft(job_id: str, tenant_id: str = "default") -> str | None:
    return get_prep_drafts(tenant_id).get(job_id) or None


def save_cover_letter_draft(job_id: str, body: str, *, tenant_id: str = "default") -> None:
    set_prep_cover_draft(job_id, body, tenant_id=tenant_id)


def get_reach_out_saved(job_id: str, tenant_id: str = "default") -> dict[str, Any]:
    entry = get_prep_reach_out(tenant_id).get(job_id) or {}
    contacts = entry.get("contacts") if isinstance(entry.get("contacts"), list) else []
    return {
        "contacts": contacts,
        "outreach_draft": str(entry.get("outreach_draft") or ""),
    }


def save_reach_out_contacts(
    job_id: str,
    contacts: list[dict[str, Any]],
    *,
    tenant_id: str = "default",
) -> dict[str, Any]:
    return set_prep_reach_out_entry(job_id, contacts=contacts, tenant_id=tenant_id)


def save_outreach_draft(
    job_id: str,
    body: str,
    *,
    tenant_id: str = "default",
) -> dict[str, Any]:
    return set_prep_reach_out_entry(job_id, outreach_draft=body, tenant_id=tenant_id)
