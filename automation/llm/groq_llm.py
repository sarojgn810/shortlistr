"""
shortlistr LLM — Groq adapter (groq.com fast inference — NOT xAI's Grok)

Groq's API is OpenAI-compatible, so this reuses the openai SDK against
https://api.groq.com/openai/v1 — no extra dependency.

Requires:  pip install openai
API key:   set SHORTLISTR_LLM_API_KEY in .env (Groq keys start with "gsk_")
Models:    llama-3.3-70b-versatile (default), llama-3.1-8b-instant (fast/cheap)
"""

import logging

from .base import LLMProvider

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "llama-3.3-70b-versatile"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"


class GroqProvider(LLMProvider):

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL):
        self.api_key = api_key
        self.model = model or DEFAULT_MODEL
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from openai import OpenAI

                self._client = OpenAI(api_key=self.api_key, base_url=GROQ_BASE_URL)
            except ImportError:
                raise RuntimeError(
                    "openai package not installed (Groq uses the OpenAI-compatible "
                    "client). Run: pip install openai"
                )
        return self._client

    def complete(self, prompt: str, system: str = "", max_tokens: int = 1024) -> str:
        client = self._get_client()
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Groq API error: {e}")
            raise RuntimeError(f"Groq request failed: {e}") from e

    @classmethod
    def sdk_available(cls) -> bool:
        import importlib.util

        return importlib.util.find_spec("openai") is not None

    @classmethod
    def install_hint(cls) -> str:
        return "pip install openai"

    def is_available(self) -> bool:
        return bool(self.api_key)

    def __repr__(self):
        return f"<GroqProvider model={self.model}>"
