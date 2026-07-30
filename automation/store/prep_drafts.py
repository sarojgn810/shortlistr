"""Saved prep drafts (cover letters) per job."""

from __future__ import annotations

from store.settings import get_prep_drafts, set_prep_cover_draft


def get_cover_letter_draft(job_id: str, tenant_id: str = "default") -> str | None:
    return get_prep_drafts(tenant_id).get(job_id) or None


def save_cover_letter_draft(job_id: str, body: str, *, tenant_id: str = "default") -> None:
    set_prep_cover_draft(job_id, body, tenant_id=tenant_id)
