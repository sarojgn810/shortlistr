"""
shortlistr LLM — OpenAI adapter

Requires:  pip install openai
API key:   set SHORTLISTR_LLM_API_KEY in .env or config/profile.yml
Models:    gpt-4o (default), gpt-4o-mini (fast/cheap), gpt-4-turbo
"""

import logging
from .base import LLMProvider

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-4o"


class OpenAIProvider(LLMProvider):

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL):
        self.api_key = api_key
        self.model   = model or DEFAULT_MODEL
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from openai import OpenAI
                self._client = OpenAI(api_key=self.api_key)
            except ImportError:
                raise RuntimeError(
                    "openai package not installed. Run: pip install openai"
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
            logger.error(f"OpenAI API error: {e}")
            raise RuntimeError(f"OpenAI request failed: {e}") from e

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
        return f"<OpenAIProvider model={self.model}>"
