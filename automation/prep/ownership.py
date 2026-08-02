"""Stamp and verify prep artifacts belong to the live profile.

Interview-prep files used to be looked up by company name only. Copying an
``interview-prep/`` folder (or sharing a machine image) then surfaced another
person's proof points and skills under the wrong job. Every guide is now keyed
by ``job_id`` and stamped with the profile owner; foreign stamps are ignored.
"""

from __future__ import annotations

import os
import re
from typing import Any


def owner_key() -> str:
    """Stable identity for the person this machine is preparing materials for."""
    try:
        from config import CANDIDATE

        cand = CANDIDATE or {}
        email = str(cand.get("email") or "").strip().lower()
        if email:
            return email
        name = str(cand.get("name") or "").strip().lower()
        if name:
            return name
    except Exception:
        pass
    return ""


def parse_front_matter(text: str) -> tuple[dict[str, str], str]:
    """Return (meta, body) for ``---\\nkey: value\\n---`` docs; else ({}, text)."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end < 0:
        return {}, text
    block = text[3:end].strip()
    body = text[end + 4 :].lstrip("\n")
    meta: dict[str, str] = {}
    for line in block.splitlines():
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        meta[key.strip().lower()] = val.strip()
    return meta, body


def front_matter(*, job_id: str, owner: str, company: str = "", role: str = "") -> str:
    lines = ["---", f"job_id: {job_id}", f"owner: {owner or 'unknown'}"]
    if company:
        lines.append(f"company: {company}")
    if role:
        lines.append(f"role: {role}")
    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def is_ours(meta: dict[str, str], *, job_id: str, owner: str | None = None) -> bool:
    """True when front matter claims this job and (if known) this owner."""
    if not meta:
        return False
    if str(meta.get("job_id") or "").strip() != str(job_id).strip():
        return False
    expected = (owner if owner is not None else owner_key()).strip().lower()
    stamped = str(meta.get("owner") or "").strip().lower()
    if not expected:
        # No profile yet — accept job_id match only.
        return True
    if not stamped or stamped in ("unknown", "none"):
        return False
    return stamped == expected


def prep_path_for_job(job_id: str, prep_dir: str | None = None) -> str:
    from config import PREP_DIR

    root = prep_dir or PREP_DIR
    safe = re.sub(r"[^a-zA-Z0-9_-]", "", str(job_id or ""))[:64] or "job"
    return os.path.join(root, f"{safe}.md")


def load_owned_prep(
    job_id: str,
    *,
    prep_dir: str | None = None,
    url: str = "",
) -> tuple[str | None, str | None]:
    """Return ``(path, content)`` for an owned prep guide, else ``(None, None)``.

    Never returns another profile's file. Legacy company-named files are only
    accepted when they carry matching ``job_id`` + ``owner`` front matter (or,
    for unstamped legacy, when the Job URL line matches *and* no foreign owner).
    """
    from config import PREP_DIR

    root = prep_dir or PREP_DIR
    owner = owner_key()
    primary = prep_path_for_job(job_id, root)
    candidates: list[str] = []
    if os.path.isfile(primary):
        candidates.append(primary)
    if os.path.isdir(root):
        for name in sorted(os.listdir(root), reverse=True):
            if not name.endswith(".md"):
                continue
            path = os.path.join(root, name)
            if path == primary:
                continue
            candidates.append(path)

    for path in candidates:
        try:
            raw = open(path, encoding="utf-8").read()
        except OSError:
            continue
        meta, body = parse_front_matter(raw)
        if is_ours(meta, job_id=job_id, owner=owner):
            return path, raw
        # Never reuse unstamped or foreign guides (copied installs).
        continue
    return None, None


def display_fit(job_row: dict[str, Any]) -> dict[str, Any]:
    """Normalize discovery + eval scores for the Prep UI."""
    discovery = job_row.get("fit_score")
    try:
        discovery_n = float(discovery) if discovery is not None else 0.0
    except (TypeError, ValueError):
        discovery_n = 0.0
    eval_score = job_row.get("eval_score")
    try:
        eval_n = float(eval_score) if eval_score is not None else None
    except (TypeError, ValueError):
        eval_n = None
    # Prefer A–G eval (0–5). Else show discovery as /100.
    if eval_n is not None and eval_n > 0:
        label = f"{eval_n:.1f}/5"
        primary = eval_n
        scale = "eval"
    elif discovery_n > 0:
        label = f"{discovery_n:.0f}/100"
        primary = discovery_n
        scale = "discovery"
    else:
        label = "—"
        primary = 0
        scale = "none"
    return {
        "fit_score": discovery_n,
        "eval_score": eval_n,
        "fit_reason": (job_row.get("fit_reason") or "")[:400],
        "fit_label": label,
        "fit_primary": primary,
        "fit_scale": scale,
        "candidate_name": (job_row.get("candidate_name") or ""),
    }
