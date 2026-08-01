"""Two-stage LLM triage — cheap gate before full A–G evaluation.

When enabled (``llm.two_stage_triage: true``), a short JSON triage runs first.
Obvious mismatches skip the full prompt and return a light template-style result.
Failures / unclear triage always fall through to the full evaluation.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_TRIAGE_SYSTEM = (
    "You are a fast job-fit triage. Given a short CV excerpt and JD excerpt, "
    "return ONLY JSON: {\"proceed\": true|false, \"score_guess\": 0-5 number, "
    "\"reason\": \"one short sentence\"}. "
    "proceed=false only when clearly wrong title family, seniority, or location. "
    "When unsure, proceed=true."
)


def triage_enabled() -> bool:
    try:
        from config import LLM_CONFIG, _PROFILE

        llm = LLM_CONFIG or {}
        flag = llm.get("two_stage_triage")
        if isinstance(flag, bool):
            if flag:
                return True
        elif str(flag or "").lower() in ("true", "1", "yes"):
            return True
        raw = _PROFILE.get("llm") if isinstance(_PROFILE.get("llm"), dict) else {}
        return str(raw.get("two_stage_triage", "")).lower() in ("true", "1", "yes")
    except Exception:
        return False


def run_triage(
    *,
    jd_text: str,
    cv_text: str,
    company: str = "",
    role: str = "",
    url: str = "",
) -> dict[str, Any] | None:
    """Return triage dict or None if unavailable / parse failure."""
    from llm import get_llm

    provider = get_llm()
    if not provider or not provider.is_available():
        return None
    user = (
        f"Company: {company}\nRole: {role}\nURL: {url}\n\n"
        f"--- CV (excerpt) ---\n{(cv_text or '')[:1800]}\n\n"
        f"--- JD (excerpt) ---\n{(jd_text or '')[:2500]}"
    )
    try:
        raw = provider.complete(user, system=_TRIAGE_SYSTEM, max_tokens=200)
        m = re.search(r"\{[\s\S]*\}", raw or "")
        if not m:
            return None
        data = json.loads(m.group(0))
        if not isinstance(data, dict):
            return None
        proceed = data.get("proceed")
        if isinstance(proceed, str):
            proceed = proceed.lower() in ("true", "1", "yes")
        return {
            "proceed": bool(proceed) if proceed is not None else True,
            "score_guess": float(data.get("score_guess") or 0),
            "reason": str(data.get("reason") or "")[:300],
        }
    except Exception as exc:
        logger.debug("triage failed: %s", exc)
        return None
