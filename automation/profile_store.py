"""Read/write config/profile.yml and .env secrets from the web onboarding form."""

from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Any

from config import SHORTLISTR_ROOT
from paths import PROFILE_PATH

PROFILE_EXAMPLE = os.path.join(SHORTLISTR_ROOT, "config", "profile.example.yml")
ENV_FILE = os.path.join(SHORTLISTR_ROOT, ".env")

LLM_PROVIDERS = ("none", "auto", "anthropic", "openai", "gemini", "grok", "groq", "ollama")


def _load_yaml(path: str) -> dict[str, Any]:
    import yaml

    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _default_profile() -> dict[str, Any]:
    if os.path.isfile(PROFILE_EXAMPLE):
        return _load_yaml(PROFILE_EXAMPLE)
    return {
        "candidate": {
            "name": "",
            "email": "",
            "phone": "",
            "location": "",
            "linkedin": "",
            "github": "",
            "years_exp": 0,
        },
        "filters": {
            "min_salary_inr_lpa": 0,
            "min_salary_usd": 0,
            "salary_unlisted": "include",
            "target_titles": [],
            "preferred_locations": [],
            "deal_breakers": [],
        },
        "llm": {"provider": "auto", "model": "qwen2.5:0.5b", "ollama_url": "http://localhost:11434"},
        "scoring": {"min_fit_score": 40},
    }


def _dedupe(items: list[str]) -> list[str]:
    """Drop repeats case-insensitively, keeping the first spelling and the order.

    A repeated title costs a search slot and breaks list rendering in the UI
    (React keys off the title string), so entries are unique from the moment
    they are saved.
    """
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        key = item.casefold()
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


def _parse_titles(raw: str | list[str]) -> list[str]:
    if isinstance(raw, list):
        return _dedupe([t.strip() for t in raw if str(t).strip()])
    return _dedupe([t.strip() for t in re.split(r"[,;\n]", str(raw)) if t.strip()])


def _detect_provider_from_key() -> str | None:
    """Infer LLM provider from the saved API key prefix. Returns None if unknown."""
    try:
        from secrets_store import get_secret
        key = get_secret("SHORTLISTR_LLM_API_KEY")
    except Exception:
        key = os.environ.get("SHORTLISTR_LLM_API_KEY", "")
    if not key:
        return None
    if key.startswith("sk-ant-"):
        return "anthropic"
    if key.startswith("xai-"):
        return "grok"
    if key.startswith("gsk_"):
        return "groq"
    if key.startswith("sk-"):
        return "openai"
    if key.startswith("AI") or key.startswith("ya29"):
        return "gemini"
    return None


def get_profile_for_ui() -> dict[str, Any]:
    """Safe profile payload for the dashboard (no secrets)."""
    data = _load_yaml(PROFILE_PATH) if os.path.isfile(PROFILE_PATH) else _default_profile()
    cand = data.get("candidate") or {}
    filt = data.get("filters") or {}
    llm = data.get("llm") or {}
    scoring = data.get("scoring") or {}
    app = data.get("application") or {}

    from secrets_store import has_secret

    api_key_set = has_secret("SHORTLISTR_LLM_API_KEY")

    provider = (llm.get("provider") or "none").lower()
    suggested = _detect_provider_from_key() if (provider == "none" and api_key_set) else None

    return {
        "exists": os.path.isfile(PROFILE_PATH),
        "name": cand.get("name", ""),
        "email": cand.get("email", ""),
        "phone": cand.get("phone", ""),
        "location": cand.get("location", ""),
        "linkedin": cand.get("linkedin", ""),
        "github": cand.get("github", ""),
        "years_exp": int(cand.get("years_exp") or 0),
        "min_salary_inr_lpa": int(filt.get("min_salary_inr_lpa") or 0),
        "min_salary_usd": int(filt.get("min_salary_usd") or 0),
        "salary_unlisted": filt.get("salary_unlisted", "include"),
        # Deduped on read too: profile.yml is user-editable by hand.
        "target_titles": _parse_titles(list(filt.get("target_titles") or [])),
        "preferred_locations": _parse_titles(list(filt.get("preferred_locations") or [])),
        "min_fit_score": int(scoring.get("min_fit_score") or 40),
        "llm_provider": provider,
        "llm_model": llm.get("model") or "",
        "llm_api_key_set": api_key_set,
        "suggested_provider": suggested,
        "website": app.get("website", ""),
        "notice_period": app.get("notice_period", ""),
        "current_ctc": app.get("current_ctc", ""),
        "expected_ctc": app.get("expected_ctc", ""),
        "how_heard": app.get("how_heard", ""),
        "work_authorization": app.get("work_authorization", ""),
        "preferred_name": app.get("preferred_name", ""),
        "cover_letter_snippet": app.get("cover_letter_snippet", ""),
        "willing_to_relocate": app.get("willing_to_relocate", ""),
    }


def _write_env_llm_key(api_key: str | None) -> None:
    """Store the LLM API key in the OS keychain (never plaintext .env)."""
    if api_key is None:
        return
    from secrets_store import delete_secret, set_secret

    if api_key:
        set_secret("SHORTLISTR_LLM_API_KEY", api_key)
    else:
        delete_secret("SHORTLISTR_LLM_API_KEY")

    # Ensure no stale plaintext key lingers in an existing .env.
    if os.path.isfile(ENV_FILE):
        new_lines = [
            "SHORTLISTR_LLM_API_KEY=" if ln.startswith("SHORTLISTR_LLM_API_KEY=") else ln
            for ln in open(ENV_FILE, encoding="utf-8").read().splitlines()
        ]
        with open(ENV_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(new_lines).rstrip() + "\n")


def save_profile_from_ui(body: dict[str, Any]) -> dict[str, Any]:
    """Validate and write profile.yml + optional LLM key to .env.

    Merges the incoming fields onto the current profile, so partial updates
    (e.g. the Connections LLM card sending only provider/model/key, or the
    Profile page sending only personal info) don't wipe the rest or fail
    validation on fields they didn't send.
    """
    incoming = {k: v for k, v in body.items() if v is not None}
    body = {**get_profile_for_ui(), **incoming}
    name = (body.get("name") or "").strip()
    email = (body.get("email") or "").strip()
    if not name or not email:
        raise ValueError("Name and email are required")

    provider = (body.get("llm_provider") or "none").lower()
    if provider not in LLM_PROVIDERS:
        raise ValueError(f"llm_provider must be one of: {', '.join(LLM_PROVIDERS)}")

    titles = _parse_titles(body.get("target_titles") or [])
    if not titles:
        raise ValueError("Add at least one target job title")

    locations = _parse_titles(body.get("preferred_locations") or [])

    os.makedirs(os.path.dirname(PROFILE_PATH), exist_ok=True)
    titles_yml = "\n".join(f'    - "{t}"' for t in titles)
    locs_yml = "\n".join(f'    - "{loc}"' for loc in locations) if locations else ""

    # Preserve hand-edited sections that the UI does not own (sources, discovery…).
    # A full rewrite used to wipe Apify boards and other discovery config.
    # platforms emails are owned by the Connections page — keep them unless this
    # save explicitly includes new values (first-run seed uses the candidate email).
    existing = _load_yaml(PROFILE_PATH) if os.path.isfile(PROFILE_PATH) else {}
    preserve_keys = ("sources", "discovery", "mcp_servers")
    preserved = {k: existing[k] for k in preserve_keys if k in existing and existing[k]}

    existing_platforms = existing.get("platforms") if isinstance(existing.get("platforms"), dict) else {}
    existing_li = existing_platforms.get("linkedin") if isinstance(existing_platforms.get("linkedin"), dict) else {}
    existing_nk = existing_platforms.get("naukri") if isinstance(existing_platforms.get("naukri"), dict) else {}
    li_email = (body.get("linkedin_platform_email") or existing_li.get("email") or email or "").strip()
    nk_email = (body.get("naukri_platform_email") if body.get("naukri_platform_email") is not None
                else existing_nk.get("email") or "")
    nk_email = str(nk_email or "").strip()

    existing_email = existing.get("email") if isinstance(existing.get("email"), dict) else {}
    sender = (body.get("gmail_sender") or existing_email.get("sender") or email or "").strip()

    def _q(v: Any) -> str:
        s = str(v or "").strip().replace("\\", "\\\\").replace('"', '\\"')
        return re.sub(r"\s+", " ", s)
    content = f"""# shortlistr — User Profile
# Generated by dashboard onboarding on {datetime.now().strftime('%Y-%m-%d')}

candidate:
  name: "{name}"
  email: "{email}"
  phone: "{(body.get('phone') or '').strip()}"
  location: "{(body.get('location') or '').strip()}"
  linkedin: "{(body.get('linkedin') or '').strip()}"
  github: "{(body.get('github') or '').strip()}"
  years_exp: {int(body.get('years_exp') or 0)}

files:
  resume_pdf: "resume.pdf"
  cv_markdown: "cv.md"

filters:
  min_salary_inr_lpa: {int(body.get('min_salary_inr_lpa') or 0)}
  min_salary_usd: {int(body.get('min_salary_usd') or 0)}
  salary_unlisted: "{body.get('salary_unlisted') or 'include'}"
  target_titles:
{titles_yml}
  preferred_locations:{(' []' if not locs_yml else chr(10) + locs_yml)}
  deal_breakers: []

llm:
  provider: "{provider}"
  model: "{(body.get('llm_model') or '').strip()}"
  api_key: ""
  ollama_url: "http://localhost:11434"

email:
  smtp_host: "smtp.gmail.com"
  smtp_port: 587
  sender: "{sender}"
  max_per_run: 10

platforms:
  linkedin:
    email: "{li_email}"
  naukri:
    email: "{nk_email}"

application:
  website: "{_q(body.get('website'))}"
  notice_period: "{_q(body.get('notice_period'))}"
  current_ctc: "{_q(body.get('current_ctc'))}"
  expected_ctc: "{_q(body.get('expected_ctc'))}"
  how_heard: "{_q(body.get('how_heard'))}"
  work_authorization: "{_q(body.get('work_authorization'))}"
  preferred_name: "{_q(body.get('preferred_name'))}"
  cover_letter_snippet: "{_q(body.get('cover_letter_snippet'))}"
  willing_to_relocate: "{_q(body.get('willing_to_relocate'))}"

scoring:
  min_fit_score: {int(body.get('min_fit_score') or 40)}
"""
    if preserved:
        import yaml

        content += "\n" + yaml.safe_dump(
            preserved,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )
    with open(PROFILE_PATH, "w", encoding="utf-8") as f:
        f.write(content)

    api_key = body.get("llm_api_key")
    if api_key is not None:
        key = str(api_key).strip()
        _write_env_llm_key(key if key else "")

    # Apply config changes to the running API immediately (no restart).
    try:
        from llm import reload_llm_config
        reload_llm_config()
    except Exception:
        pass
    try:
        from config import reload_discovery_config
        reload_discovery_config()
    except Exception:
        pass

    return get_profile_for_ui()


def update_target_titles_from_resume(
    target_titles: list[str],
    *,
    extracted: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist résumé-derived target titles without clobbering the rest of the profile.

    If no profile exists yet, seed a minimal one from extracted contact fields so
    discovery can retarget on first upload (before the onboarding form is saved).
    """
    titles = _parse_titles(target_titles)
    if not titles:
        return get_profile_for_ui()

    profile = get_profile_for_ui()
    extracted = extracted or {}
    payload = {**profile, "target_titles": titles}

    # First-run: fill identity from the résumé so save_profile validation passes.
    if not profile.get("exists"):
        for key in ("name", "email", "phone", "location", "linkedin", "github"):
            if extracted.get(key) and not payload.get(key):
                payload[key] = extracted[key]
        if extracted.get("years_exp") and not payload.get("years_exp"):
            payload["years_exp"] = extracted["years_exp"]
        if extracted.get("preferred_locations") and not payload.get("preferred_locations"):
            payload["preferred_locations"] = extracted["preferred_locations"]
        payload.setdefault("name", (extracted.get("name") or "Demo User").strip() or "Demo User")
        payload.setdefault("email", (extracted.get("email") or "demo@example.com").strip() or "demo@example.com")
        payload.setdefault("preferred_locations", ["Remote"])
        payload.setdefault("llm_provider", "auto")

    return save_profile_from_ui(payload)


def seed_starter_profile_if_missing() -> str | None:
    """No-op: profile is created in onboarding from the user's résumé.

    Kept as a callable for older bootstrap callers / tests. Writing a fictional
    person here used to poison discovery (author titles) before first upload.
    """
    if os.path.isfile(PROFILE_PATH):
        return None
    return None

