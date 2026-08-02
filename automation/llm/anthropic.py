"""
shortlistr LLM — Anthropic API adapter

Requires:  pip install anthropic
API key:   set SHORTLISTR_LLM_API_KEY in .env or config/profile.yml
"""

import logging
from .base import LLMProvider

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-3-5-sonnet-20241022"


class AnthropicProvider(LLMProvider):

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL):
        self.api_key = api_key
        self.model   = model or DEFAULT_MODEL
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                import anthropic
                self._client = anthropic.Anthropic(api_key=self.api_key)
            except ImportError:
                raise RuntimeError(
                    "anthropic package not installed. Run: pip install anthropic"
                )
        return self._client

    def complete(self, prompt: str, system: str = "", max_tokens: int = 1024) -> str:
        client = self._get_client()
        kwargs = {
            "model":      self.model,
            "max_tokens": max_tokens,
            "messages":   [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system

        try:
            response = client.messages.create(**kwargs)
            return response.content[0].text.strip()
        except Exception as e:
            logger.error(f"Anthropic API error: {e}")
            raise RuntimeError(f"Anthropic request failed: {e}") from e

    @classmethod
    def sdk_available(cls) -> bool:
        import importlib.util
        return importlib.util.find_spec("anthropic") is not None

    @classmethod
    def install_hint(cls) -> str:
        return "pip install anthropic"

    def is_available(self) -> bool:
        return bool(self.api_key)

    def __repr__(self):
        return f"<AnthropicProvider model={self.model}>"
