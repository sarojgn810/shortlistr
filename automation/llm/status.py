"""LLM configuration status — safe for API/dashboard (no secrets)."""

from __future__ import annotations

import os


def llm_status() -> dict:
    """Return provider, model, and availability without exposing API keys."""
    try:
        from config import LLM_CONFIG
    except ImportError:
        LLM_CONFIG = {}

    provider = str(LLM_CONFIG.get("provider") or "none").lower().strip()
    model = str(LLM_CONFIG.get("model") or "")
    api_key = str(LLM_CONFIG.get("api_key") or "")
    if not api_key:
        try:
            from secrets_store import get_secret

            api_key = get_secret("SHORTLISTR_LLM_API_KEY")
        except Exception:
            api_key = os.environ.get("SHORTLISTR_LLM_API_KEY", "")

    configured = provider not in ("", "none")
    # auto / ollama never need a cloud API key
    api_key_set = True if provider in ("ollama", "auto") else bool(api_key.strip())

    available = False
    resolved = provider
    resolved_model = model
    if configured:
        try:
            from llm import coerce_cloud_model, get_llm, resolved_provider_name

            # Heal Ollama tags left on a cloud provider before building the client.
            if provider in ("groq", "openai", "anthropic", "gemini", "grok"):
                healed = coerce_cloud_model(provider, model)
                if healed != model:
                    try:
                        from llm import _persist_coerced_model

                        _persist_coerced_model(provider, model, healed)
                    except Exception:
                        LLM_CONFIG["model"] = healed
                    model = healed
                    # Force rebuild so a stale GroqProvider(qwen…) is dropped.
                    llm = get_llm(force_reload=True)
                else:
                    llm = get_llm()
            else:
                llm = get_llm()
            available = bool(llm and llm.is_available())
            resolved = resolved_provider_name() or provider
            if llm is not None and getattr(llm, "model", None):
                resolved_model = str(llm.model)
        except Exception:
            available = False

    # SDK presence + a machine-readable reason/hint so the UI can tell the user
    # exactly why full A-G scoring is or isn't active (instead of silently showing
    # template results while claiming "LLM mode").
    sdk_installed = True
    install_hint = ""
    check_provider = resolved if provider == "auto" and resolved not in ("", "none", "auto") else provider
    if configured and check_provider in ("anthropic", "openai", "gemini", "grok", "groq"):
        import importlib.util

        _pkg = {
            "openai": "openai",
            "anthropic": "anthropic",
            "gemini": "google.genai",
            "grok": "openai",  # xAI uses the OpenAI-compatible client
            "groq": "openai",  # so does Groq
        }[check_provider]
        sdk_installed = importlib.util.find_spec(_pkg) is not None
        if not sdk_installed:
            install_hint = {
                "openai": "pip install openai",
                "anthropic": "pip install anthropic",
                "gemini": "pip install google-genai",
                "grok": "pip install openai",
                "groq": "pip install openai",
            }[check_provider]

    if not configured:
        reason = "not_configured"
    elif provider == "auto" and not available:
        reason = "unavailable"
    elif not api_key_set:
        reason = "missing_api_key"
    elif not sdk_installed:
        reason = "sdk_missing"
    elif not available:
        reason = "unavailable"
    else:
        reason = "ok"

    hint = {
        "not_configured": "Set up Local AI on Connections (free, on this computer) or add a cloud key for full A–G scoring.",
        "missing_api_key": f"Add your {provider} API key on Connections.",
        "sdk_missing": f"Provider '{check_provider}' is selected but its SDK isn't installed. Fix from Connections or reinstall Shortlistr.",
        "unavailable": (
            "Local AI is still setting up, or isn’t reachable yet. Open Connections → Set up Local AI."
            if provider in ("auto", "ollama")
            else f"{provider} is configured but not reachable right now."
        ),
        "ok": "",
    }[reason]

    env_paths = []
    try:
        from config import SHORTLISTR_ROOT

        for rel in (".env", os.path.join("automation", ".env")):
            p = os.path.join(SHORTLISTR_ROOT, rel)
            if os.path.isfile(p):
                env_paths.append(rel)
    except ImportError:
        pass

    return {
        "provider": provider,
        "resolved_provider": resolved,
        "model": resolved_model or model,
        "configured": configured,
        "api_key_set": api_key_set,
        "available": available,
        "sdk_installed": sdk_installed,
        "reason": reason,
        "hint": hint,
        "install_hint": install_hint,
        "mode": "llm" if available else "template",
        "env_files": env_paths,
        "env_var": "SHORTLISTR_LLM_API_KEY",
        "prompt_template": "automation/eval/prompts/evaluate_v1.txt",
        "features": {
            "evaluation": available,
            "cover_letter": available,
            # Chat runs a complete()-based JSON tool loop when a provider is up.
            "tool_calling": available,
            "rag": False,
            "memory": False,
            "embeddings": False,
        },
    }
