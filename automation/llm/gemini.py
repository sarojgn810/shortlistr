"""
shortlistr LLM — Google Gemini adapter (google-genai SDK)

Requires:  pip install google-genai   (the current SDK; the old
           `google-generativeai` package is end-of-life)
API key:   set SHORTLISTR_LLM_API_KEY in .env or config/profile.yml
Models:    gemini-2.0-flash (default), gemini-2.5-flash, gemini-1.5-pro
"""

import importlib.util
import logging

from .base import LLMProvider

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-2.0-flash"


class GeminiProvider(LLMProvider):

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL):
        self.api_key = api_key
        self.model = model or DEFAULT_MODEL
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from google import genai
            except ImportError:
                raise RuntimeError(
                    "google-genai not installed. Run: pip install google-genai"
                )
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def complete(self, prompt: str, system: str = "", max_tokens: int = 1024) -> str:
        client = self._get_client()
        try:
            from google.genai import types

            config = types.GenerateContentConfig(
                max_output_tokens=max_tokens,
                system_instruction=system or None,
            )
            resp = client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=config,
            )
            return (resp.text or "").strip()
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            raise RuntimeError(f"Gemini request failed: {e}") from e

    @classmethod
    def sdk_available(cls) -> bool:
        return importlib.util.find_spec("google.genai") is not None

    @classmethod
    def install_hint(cls) -> str:
        return "pip install google-genai"

    def is_available(self) -> bool:
        return bool(self.api_key)

    def __repr__(self):
        return f"<GeminiProvider model={self.model}>"
