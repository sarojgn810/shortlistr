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
from linkedin_optimizer.roles import get_role, list_roles
from linkedin_optimizer.scorer import score_profile
from linkedin_optimizer.from_cv import corpus_text

DRAFT_PATH = os.path.join(DATA_DIR, "linkedin_optimizer.json")


def _load_draft() -> dict[str, Any]:
    if not os.path.isfile(DRAFT_PATH):
        return {}
    try:
        with open(DRAFT_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_draft(data: dict[str, Any]) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(DRAFT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _detect_role(titles: list[str] | None, fallback: str = "sre") -> str:
    if not titles:
        return fallback
    t0 = str(titles[0]).lower()
    if "sre" in t0 or "reliability" in t0:
        return "sre"
    if "devops" in t0:
        return "devops"
    if "full" in t0 and "stack" in t0:
        return "fullstack"
    if "ml" in t0 or "ai" in t0:
        return "ai_engineer"
    if "backend" in t0:
        return "backend"
    return fallback


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
    role_id = target_role or _detect_role(
        [profile.get("headline") or ""]
        + [j.get("title") or "" for j in profile.get("experience") or []],
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
    url: str | None = None, *, target_role: str = "sre", persist: bool = True
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
    out = analyze(profile=profile, target_role=target_role or "sre", persist=persist)
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
    target_role: str = "sre",
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
    score = score_profile(parsed, target_role)
    role = get_role(target_role)
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
    target_role: str = "sre",
    use_llm: bool = False,
) -> dict[str, Any]:
    if profile:
        parsed = profile_from_structured(profile)
    else:
        draft = _load_draft()
        parsed = draft.get("profile") or profile_from_structured({})
        target_role = draft.get("target_role") or target_role

    result = rewrite_section(section, parsed, target_role)
    mode = result.get("mode") or "heuristic"
    if use_llm and result.get("suggested"):
        polished, mode = maybe_llm_polish(
            result["suggested"], section, target_role, evidence=corpus_text(parsed)
        )
        result["suggested"] = polished
        result["mode"] = mode
    result["llm_attempted"] = bool(use_llm)
    return result


def rewrite_all(
    *,
    profile: dict[str, Any] | None = None,
    target_role: str = "sre",
    use_llm: bool = False,
) -> dict[str, Any]:
    sections = ["headline", "about", "experience", "skills", "open_to_work", "featured"]
    out = {}
    for s in sections:
        out[s] = rewrite(section=s, profile=profile, target_role=target_role, use_llm=use_llm)
    return {"sections": out, "target_role": get_role(target_role)["id"]}


def get_state() -> dict[str, Any]:
    draft = _load_draft()
    profile = draft.get("profile")
    url = draft.get("linkedin_url") or resolve_linkedin_url()
    role_id = draft.get("target_role") or "sre"

    # Auto-import from CV when we have no substantial draft yet
    if not _profile_is_substantial(profile) and os.path.isfile(CV_MD_PATH):
        imported = import_from_cv(target_role=role_id, persist=True)
        if imported.get("ok"):
            return {
                "profile": imported["profile"],
                "target_role": imported["target_role"],
                "score": imported["score"],
                "roles": list_roles(),
                "cover_themes": list_themes(),
                "linkedin_url": imported.get("linkedin_url") or url,
                "source": "cv",
                "substantial": True,
                "needs_import": False,
                "import_note": imported.get("import_note"),
            }

    if not profile:
        profile = profile_from_structured({})
    score = draft.get("score") or score_profile(profile, role_id)
    substantial = _profile_is_substantial(profile)
    return {
        "profile": profile,
        "target_role": role_id,
        "score": score,
        "roles": list_roles(),
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


def save_state(profile: dict[str, Any], target_role: str) -> dict[str, Any]:
    return analyze(profile=profile, target_role=target_role, persist=True)


def render_cover(payload: dict[str, Any]) -> dict[str, Any]:
    return render_cover_data_uri(
        theme_id=str(payload.get("theme_id") or "ink_lime"),
        name=str(payload.get("name") or ""),
        headline=str(payload.get("headline") or ""),
        subline=str(payload.get("subline") or ""),
    )
