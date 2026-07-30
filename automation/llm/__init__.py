"""
shortlistr LLM — Provider factory

Usage:
    from llm import get_llm

    llm = get_llm()          # reads config/profile.yml automatically
    if llm:
        text = llm.complete("Write a cover letter for...")
    else:
        text = fallback_template(...)

Supported providers (set in config/profile.yml → llm.provider):
    auto      → Prefer Local AI (Ollama tiny model), else cloud key, else templates
    anthropic → Anthropic API
    openai    → OpenAI GPT
    gemini    → Google Gemini
    grok      → xAI Grok (OpenAI-compatible API)
    groq      → Groq fast inference (Llama models; OpenAI-compatible API)
    ollama    → Local Ollama (no API key needed)
    none      → No LLM; returns None — use template fallback
"""

import os
import logging
from typing import Optional
from .base import LLMProvider

logger = logging.getLogger(__name__)

_cached_llm: Optional[LLMProvider] = None
_cache_loaded = False
_cached_resolved: str = ""


def reload_llm_config() -> Optional[LLMProvider]:
    """Re-read profile.yml's llm section into config.LLM_CONFIG and rebuild the
    provider, so a key/provider saved via the dashboard applies without an API
    restart. Returns the freshly-built provider (or None)."""
    # Use the same profile path config.py loads. (This file is automation/llm/__init__.py,
    # so the repo root is THREE levels up — the old two-level path pointed at a
    # non-existent automation/config/profile.yml, so live LLM re-config silently no-op'd.)
    try:
        import config as _cfg

        profile_yml = _cfg.PROFILE_PATH
    except Exception:
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        profile_yml = os.path.join(root, "config", "profile.yml")
    fresh = {}
    if os.path.isfile(profile_yml):
        try:
            fresh = _parse_llm_section(profile_yml)
        except Exception as e:  # pragma: no cover
            logger.warning(f"reload_llm_config: could not parse {profile_yml}: {e}")
    try:
        import config

        for key in ("provider", "model", "ollama_url"):
            if key in fresh:
                config.LLM_CONFIG[key] = fresh[key]
    except Exception:
        pass
    return get_llm(force_reload=True)


def _build_cloud(provider: str, api_key: str, model: str) -> Optional[LLMProvider]:
    if provider == "anthropic":
        from .anthropic import AnthropicProvider

        return AnthropicProvider(api_key=api_key, model=model)
    if provider == "openai":
        from .openai_llm import OpenAIProvider

        return OpenAIProvider(api_key=api_key, model=model)
    if provider == "gemini":
        from .gemini import GeminiProvider

        return GeminiProvider(api_key=api_key, model=model)
    if provider == "grok":
        from .grok import GrokProvider

        return GrokProvider(api_key=api_key, model=model)
    if provider == "groq":
        from .groq_llm import GroqProvider

        return GroqProvider(api_key=api_key, model=model)
    return None


def _sdk_ok(provider: str) -> bool:
    _CLASSES = {
        "anthropic": (".anthropic", "AnthropicProvider"),
        "openai": (".openai_llm", "OpenAIProvider"),
        "gemini": (".gemini", "GeminiProvider"),
        "grok": (".grok", "GrokProvider"),
        "groq": (".groq_llm", "GroqProvider"),
        "ollama": (".ollama", "OllamaProvider"),
    }
    entry = _CLASSES.get(provider)
    if not entry:
        return True
    import importlib

    try:
        cls = getattr(importlib.import_module(entry[0], __package__), entry[1])
    except Exception:
        return False
    return bool(cls.sdk_available())


def _resolve_auto(api_key: str, model: str, ollama_url: str) -> tuple[Optional[LLMProvider], str]:
    """Pick the best available option for a non-technical user.

    Order: Local AI ready → cloud key (auto-detect provider) → none (heuristics).
    """
    from .local_ai import RECOMMENDED_MODEL, is_local_ready
    from .ollama import OllamaProvider

    local_model = model.strip() if model.strip() and ":" in model else RECOMMENDED_MODEL
    if is_local_ready(ollama_url, local_model) or is_local_ready(ollama_url, RECOMMENDED_MODEL):
        use = local_model if is_local_ready(ollama_url, local_model) else RECOMMENDED_MODEL
        return OllamaProvider(model=use, base_url=ollama_url), "ollama"

    if api_key:
        detected = None
        try:
            from profile_store import _detect_provider_from_key

            detected = _detect_provider_from_key()
        except Exception:
            detected = None
        if detected and _sdk_ok(detected):
            cloud = _build_cloud(detected, api_key, model)
            if cloud is not None:
                return cloud, detected

    return None, "none"


def get_llm(force_reload: bool = False) -> Optional[LLMProvider]:
    """
    Return the configured LLM provider, or None if provider is 'none'.

    Reads from:
      1. config/profile.yml  (provider, model, ollama_url)
      2. .env / environment  (SHORTLISTR_LLM_API_KEY)

    Returns None if provider is 'none' or not configured — callers should
    fall back to template-based behaviour.

    ``auto`` prefers Local AI when the tiny model is ready, else a cloud key
    if present, else None.
    """
    global _cached_llm, _cache_loaded, _cached_resolved

    if _cache_loaded and not force_reload:
        return _cached_llm

    _cache_loaded = True
    _cached_resolved = ""

    cfg = _load_llm_config()
    provider = cfg.get("provider", "none").lower().strip()

    if not provider or provider == "none":
        _cached_llm = None
        _cached_resolved = "none"
        return None

    try:
        from secrets_store import get_secret as _secret
    except Exception:
        def _secret(name: str, default: str = "") -> str:
            return os.environ.get(name, default)
    api_key = cfg.get("api_key") or _secret("SHORTLISTR_LLM_API_KEY")
    model = cfg.get("model", "")
    ollama_url = cfg.get("ollama_url", "http://localhost:11434")

    if provider == "auto":
        try:
            _cached_llm, _cached_resolved = _resolve_auto(api_key or "", model or "", ollama_url)
            if _cached_llm:
                logger.info("LLM provider (auto → %s): %s", _cached_resolved, _cached_llm)
            return _cached_llm
        except Exception as e:
            logger.warning("LLM auto-resolve failed: %s — using templates", e)
            _cached_llm = None
            _cached_resolved = "none"
            return None

    # Key-requiring providers with no key = unavailable. Treat as no provider so
    # callers degrade cleanly (eval → template, chat → command fallback) instead
    # of constructing a client that 401s on first use. (ollama needs no key.)
    if provider in ("anthropic", "openai", "gemini", "grok", "groq") and not api_key:
        _cached_llm = None
        _cached_resolved = "none"
        return None

    if provider in ("anthropic", "openai", "gemini", "grok", "groq") and not _sdk_ok(provider):
        logger.warning(
            "LLM provider '%s' selected but its SDK is not installed — using template mode.",
            provider,
        )
        _cached_llm = None
        _cached_resolved = "none"
        return None

    try:
        if provider in ("anthropic", "openai", "gemini", "grok", "groq"):
            _cached_llm = _build_cloud(provider, api_key, model)
            _cached_resolved = provider if _cached_llm else "none"

        elif provider == "ollama":
            from .ollama import OllamaProvider
            from .local_ai import RECOMMENDED_MODEL

            use_model = model or RECOMMENDED_MODEL
            _cached_llm = OllamaProvider(model=use_model, base_url=ollama_url)
            _cached_resolved = "ollama"

        else:
            logger.warning(f"Unknown LLM provider '{provider}' — falling back to templates")
            _cached_llm = None
            _cached_resolved = "none"

        if _cached_llm:
            logger.info(f"LLM provider: {_cached_llm}")

    except Exception as e:
        logger.warning(f"LLM setup failed ({provider}): {e} — falling back to templates")
        _cached_llm = None
        _cached_resolved = "none"

    return _cached_llm


def resolved_provider_name() -> str:
    """Which backend ``get_llm`` last selected (useful for status / UI)."""
    if not _cache_loaded:
        get_llm()
    return _cached_resolved or "none"


def _load_llm_config() -> dict:
    """Load LLM config from repo-root config/profile.yml."""
    try:
        from config import LLM_CONFIG
        return dict(LLM_CONFIG)
    except ImportError:
        pass

    shortlistr_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    profile_yml = os.path.join(shortlistr_root, "config", "profile.yml")
    legacy = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config", "profile.yml")

    for path in (profile_yml, legacy):
        if os.path.exists(path):
            try:
                return _parse_llm_section(path)
            except Exception as e:
                logger.warning(f"Could not read LLM config from {path}: {e}")
    return {}


def _parse_llm_section(path: str) -> dict:
    """
    Minimal YAML parser for the llm: section only.
    Avoids requiring PyYAML as a hard dependency.
    """
    result = {}
    in_llm = False

    with open(path, encoding="utf-8") as f:
        for line in f:
            stripped = line.rstrip()

            if stripped.startswith("llm:"):
                in_llm = True
                continue

            # Any new top-level key ends the llm section
            if in_llm and stripped and not stripped.startswith(" ") and not stripped.startswith("#"):
                break

            if in_llm and ":" in stripped:
                # Strip leading spaces and comments
                clean = stripped.strip()
                if clean.startswith("#"):
                    continue
                key, _, val = clean.partition(":")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                # Strip inline comments
                if "#" in val:
                    val = val[:val.index("#")].strip()
                result[key] = val

    # Coerce booleans
    for k, v in result.items():
        if v.lower() == "true":
            result[k] = True
        elif v.lower() == "false":
            result[k] = False

    return result
