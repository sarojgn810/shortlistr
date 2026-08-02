"""LinkedIn optimizer orchestration — CV/URL import, grounded rewrites."""

from __future__ import annotations

import json
import os
from typing import Any

from config import CV_MD_PATH, DATA_DIR
from linkedin_optimizer.cover import list_themes, render_cover_data_uri
from linkedin_optimizer.from_cv import profile_from_cv_markdown
from linkedin_optimizer.import_profile import fetch_public_profile, normalize_linkedin_url
from linkedin_optimizer.parser import parse_profile_text, profile_from_structured
from linkedin_optimizer.rewriter import maybe_llm_polish, rewrite_section
from linkedin_optimizer.roles import (
    detect_role_id,
    get_role,
    list_roles,
    profile_titles_for_ui,
    role_from_profile,
)
from linkedin_optimizer.scorer import score_profile
from linkedin_optimizer.from_cv import corpus_text

DRAFT_PATH = os.path.join(DATA_DIR, "linkedin_optimizer.json")


def _owner_key() -> str:
    """Identity stamp so a draft from another machine/profile is not reused."""
    try:
        from config import CANDIDATE

        email = str(CANDIDATE.get("email") or "").strip().lower()
        name = str(CANDIDATE.get("name") or "").strip().lower()
        return email or name
    except Exception:
        return ""


def _is_stale_draft(data: dict[str, Any]) -> bool:
    current = _owner_key()
    if not current:
        return False
    saved = str(data.get("owner") or "").strip().lower()
    if saved and saved != current:
        return True
    if not saved:
        pname = str((data.get("profile") or {}).get("name") or "").strip().lower()
        try:
            from config import CANDIDATE

            cname = str(CANDIDATE.get("name") or "").strip().lower()
        except Exception:
            cname = ""
        if pname and cname and pname != cname:
            return True
    return False


def _repair_stored_profile(data: dict[str, Any]) -> None:
    """Drop stored fields an older parser filled in wrongly.

    A saved draft outlives the code that wrote it. An earlier parser took "a
    line under 60 characters containing a comma" as the location, which stored
    "**Site Reliability Engineer" — and because the draft is read straight back,
    the LinkedIn page kept showing it long after the parser was fixed.

    Only values that fail today's validation are cleared, so a correct one is
    never thrown away, and the field simply re-fills on the next import.
    """
    profile = data.get("profile")
    if not isinstance(profile, dict):
        return
    from linkedin_optimizer.parser import looks_like_location, looks_like_person_name

    location = str(profile.get("location") or "").strip()
    if location and not looks_like_location(location):
        profile["location"] = ""
    name = str(profile.get("name") or "").strip()
    if name and not looks_like_person_name(name):
        profile["name"] = ""


def _load_draft() -> dict[str, Any]:
    if not os.path.isfile(DRAFT_PATH):
        return {}
    try:
        with open(DRAFT_PATH, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {}
        if _is_stale_draft(data):
            return {}
        _repair_stored_profile(data)
        return data
    except Exception:
        return {}


def _save_draft(data: dict[str, Any]) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    payload = dict(data)
    owner = _owner_key()
    if owner:
        payload["owner"] = owner
    with open(DRAFT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def _resolve_role(explicit: str | None = None, *hints: str) -> str:
    """Prefer an explicit UI choice; else live profile.yml titles; else hints."""
    if (explicit or "").strip():
        return get_role(explicit)["id"]
    from_profile = role_from_profile()
    if from_profile:
        return from_profile
    hint_bits = [h for h in hints if (h or "").strip()]
    if hint_bits:
        return detect_role_id(*hint_bits)
    return ""


def _profile_linkedin_url() -> str:
    try:
        from profile_store import get_profile_for_ui

        ui = get_profile_for_ui()
        return normalize_linkedin_url(ui.get("linkedin") or "")
    except Exception:
        return ""


def _cv_linkedin_url() -> str:
    if not os.path.isfile(CV_MD_PATH):
        return ""
    try:
        with open(CV_MD_PATH, encoding="utf-8") as f:
            md = f.read()
        from cv.profile_extract import _LINKEDIN_RE, _clean_url

        m = _LINKEDIN_RE.search(md)
        return _clean_url(m.group(0)) if m else ""
    except Exception:
        return ""


def resolve_linkedin_url(explicit: str | None = None) -> str:
    return (
        normalize_linkedin_url(explicit or "")
        or _profile_linkedin_url()
        or _cv_linkedin_url()
    )


def _profile_is_substantial(profile: dict[str, Any] | None) -> bool:
    if not profile:
        return False
    about = (profile.get("about") or "").strip()
    exp = profile.get("experience") or []
    skills = profile.get("skills") or []
    bullets = sum(len(j.get("bullets") or []) for j in exp)
    return bool(about and len(about) > 80 and (bullets >= 2 or len(skills) >= 5))


def import_from_cv(*, target_role: str | None = None, persist: bool = True) -> dict[str, Any]:
    if not os.path.isfile(CV_MD_PATH):
        return {
            "ok": False,
            "error": "No résumé found (cv.md). Upload a résumé first, or paste LinkedIn text.",
            "profile": None,
        }
    with open(CV_MD_PATH, encoding="utf-8") as f:
        md = f.read()
    profile = profile_from_cv_markdown(md)
    if not _profile_is_substantial(profile):
        return {
            "ok": False,
            "error": "Résumé did not yield enough profile text. Paste your LinkedIn sections.",
            "profile": profile,
        }
    role_id = _resolve_role(
        target_role,
        profile.get("headline") or "",
        *[j.get("title") or "" for j in profile.get("experience") or []],
    )
    # Prefer URL from CV/profile
    url = profile.get("linkedin_url") or resolve_linkedin_url()
    if url:
        profile["linkedin_url"] = url
    out = analyze(profile=profile, target_role=role_id, persist=persist)
    out["ok"] = True
    out["source"] = "cv"
    out["linkedin_url"] = url
    out["import_note"] = (
        "Scored from your local résumé (ground truth). LinkedIn public pages are "
        "usually login-walled — paste LinkedIn text if you want section-for-section parity."
    )
    return out


def import_from_url(
    url: str | None = None, *, target_role: str | None = None, persist: bool = True
) -> dict[str, Any]:
    resolved = resolve_linkedin_url(url)
    if not resolved:
        return {
            "ok": False,
            "needs_url": True,
            "error": "Add your LinkedIn profile URL to continue (e.g. https://www.linkedin.com/in/you).",
            "linkedin_url": "",
            "profile": None,
        }
    fetched = fetch_public_profile(resolved)
    if not fetched.get("ok"):
        # Honest failure — offer CV fallback metadata
        cv_available = os.path.isfile(CV_MD_PATH)
        return {
            "ok": False,
            "needs_url": False,
            "linkedin_url": resolved,
            "error": fetched.get("error") or "Could not read LinkedIn profile.",
            "cv_fallback_available": cv_available,
            "profile": None,
            "via": fetched.get("via"),
        }
    profile = fetched["profile"]
    role_id = _resolve_role(
        target_role,
        profile.get("headline") or "",
        *[j.get("title") or "" for j in profile.get("experience") or []],
    )
    out = analyze(profile=profile, target_role=role_id, persist=persist)
    out["ok"] = True
    out["source"] = "linkedin"
    out["linkedin_url"] = resolved
    out["partial"] = fetched.get("partial")
    out["hint"] = fetched.get("hint") or ""
    out["import_note"] = "Imported from public LinkedIn page (may be partial)."
    return out


def analyze(
    *,
    text: str | None = None,
    profile: dict[str, Any] | None = None,
    target_role: str | None = None,
    persist: bool = True,
    linkedin_url: str | None = None,
) -> dict[str, Any]:
    if profile:
        parsed = profile_from_structured(profile)
        # Preserve source/url if present
        for k in ("linkedin_url", "source"):
            if profile.get(k) and not parsed.get(k):
                parsed[k] = profile[k]
    else:
        parsed = parse_profile_text(text or "")
        parsed["source"] = "paste"
    url = normalize_linkedin_url(linkedin_url or "") or parsed.get("linkedin_url") or resolve_linkedin_url()
    if url:
        parsed["linkedin_url"] = url
    role_id = _resolve_role(
        target_role,
        parsed.get("headline") or "",
        *[j.get("title") or "" for j in parsed.get("experience") or []],
    )
    score = score_profile(parsed, role_id)
    role = get_role(role_id)
    out = {
        "profile": parsed,
        "score": score,
        "target_role": role["id"],
        "role": {"id": role["id"], "label": role["label"], "search_titles": role["search_titles"]},
        "beats": role.get("about_beats") or [],
        "linkedin_url": parsed.get("linkedin_url") or "",
        "source": parsed.get("source") or "paste",
        "substantial": _profile_is_substantial(parsed),
    }
    if persist:
        _save_draft(
            {
                "profile": parsed,
                "target_role": role["id"],
                "score": score,
                "linkedin_url": out["linkedin_url"],
                "source": out["source"],
            }
        )
    return out


def rewrite(
    *,
    section: str,
    profile: dict[str, Any] | None = None,
    target_role: str | None = None,
    use_llm: bool = False,
) -> dict[str, Any]:
    if profile:
        parsed = profile_from_structured(profile)
        role_id = _resolve_role(target_role, parsed.get("headline") or "")
    else:
        draft = _load_draft()
        parsed = draft.get("profile") or profile_from_structured({})
        role_id = _resolve_role(
            target_role or draft.get("target_role"),
            parsed.get("headline") or "",
        )

    result = rewrite_section(section, parsed, role_id)
    mode = result.get("mode") or "heuristic"
    if use_llm and result.get("suggested"):
        polished, mode = maybe_llm_polish(
            result["suggested"], section, role_id, evidence=corpus_text(parsed)
        )
        result["suggested"] = polished
        result["mode"] = mode
    result["llm_attempted"] = bool(use_llm)
    return result


def rewrite_all(
    *,
    profile: dict[str, Any] | None = None,
    target_role: str | None = None,
    use_llm: bool = False,
) -> dict[str, Any]:
    sections = ["headline", "about", "experience", "skills", "open_to_work", "featured"]
    out = {}
    role_id = _resolve_role(target_role)
    for s in sections:
        out[s] = rewrite(section=s, profile=profile, target_role=role_id, use_llm=use_llm)
    return {"sections": out, "target_role": get_role(role_id)["id"]}


def get_state() -> dict[str, Any]:
    draft = _load_draft()
    profile = draft.get("profile")
    url = draft.get("linkedin_url") or resolve_linkedin_url()
    # Profile targeting titles are the product source of truth for Target role.
    # A leftover draft role must not override live profile.yml titles.
    profile_role = role_from_profile()
    draft_role = None
    if not profile_role and draft and _profile_is_substantial(profile):
        draft_role = draft.get("target_role")
    role_id = _resolve_role(draft_role)

    # Auto-import from CV when we have no substantial draft yet
    if not _profile_is_substantial(profile) and os.path.isfile(CV_MD_PATH):
        imported = import_from_cv(target_role=None, persist=True)
        if imported.get("ok"):
            return {
                "profile": imported["profile"],
                "target_role": imported["target_role"],
                "score": imported["score"],
                "roles": list_roles(),
                "profile_target_titles": profile_titles_for_ui(),
                "cover_themes": list_themes(),
                "linkedin_url": imported.get("linkedin_url") or url,
                "source": "cv",
                "substantial": True,
                "needs_import": False,
                "import_note": imported.get("import_note"),
            }

    if not profile:
        profile = profile_from_structured({})
        # Prefer candidate name from live profile so the UI isn't blank/wrong.
        try:
            from config import CANDIDATE

            if CANDIDATE.get("name") and not profile.get("name"):
                profile["name"] = CANDIDATE["name"]
        except Exception:
            pass
    score = draft.get("score") or score_profile(profile, role_id)
    substantial = _profile_is_substantial(profile)
    return {
        "profile": profile,
        "target_role": role_id,
        "score": score,
        "roles": list_roles(),
        "profile_target_titles": profile_titles_for_ui(),
        "cover_themes": list_themes(),
        "linkedin_url": url,
        "source": draft.get("source") or profile.get("source") or "",
        "substantial": substantial,
        "needs_import": not substantial and not url,
        "import_note": (
            None
            if substantial
            else (
                "Add your LinkedIn URL, paste profile text, or import from résumé to score real content."
            )
        ),
    }


def save_state(profile: dict[str, Any], target_role: str | None = None) -> dict[str, Any]:
    return analyze(profile=profile, target_role=target_role, persist=True)


def render_cover(payload: dict[str, Any]) -> dict[str, Any]:
    return render_cover_data_uri(
        theme_id=str(payload.get("theme_id") or "ink_lime"),
        name=str(payload.get("name") or ""),
        headline=str(payload.get("headline") or ""),
        subline=str(payload.get("subline") or ""),
    )
