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

    def complete(self, prompt: str, system: str = "", max_tokens: int = 1024,
                 json_mode: bool = False) -> str:
        # Last-line guard: a stale cache can still hold an Ollama tag after the
        # user switched to Groq (e.g. qwen2.5:0.5b → 404 model_not_found).
        if ":" in (self.model or "") and "/" not in (self.model or "").split(":", 1)[0]:
            logger.warning(
                "GroqProvider refusing Ollama-style model %r — using %s",
                self.model,
                DEFAULT_MODEL,
            )
            self.model = DEFAULT_MODEL

        client = self._get_client()
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        try:
            kwargs = {
                "model": self.model,
                "messages": messages,
                "max_tokens": max_tokens,
            }
            if json_mode:
                # Reasoning models must also be told not to think out loud.
                # Not every model accepts the field — llama-3.3-70b answers
                # "`reasoning_effort` is not supported with this model" with a
                # 400 — so the retry below drops it rather than losing the call.
                # response_format alone is not enough on a long prompt: qwen3.6
                # answered a full evaluation with 16,877 characters of "I will
                # output raw JSON starting with {" and hit the token ceiling
                # before writing any. Groq ignores this field on models that do
                # not reason, so it is safe to send unconditionally.
                kwargs["reasoning_effort"] = "none"
                # Reasoning models on Groq (the qwen3 family) answer with a
                # <think> block first and only reach the JSON if the token
                # budget outlasts it — at max_tokens=100 the object never
                # arrives at all. Asking for a JSON object suppresses the
                # preamble; measured, it turns "<think>\nHere's a thinking
                # process:…" into {"ok": true}.
                kwargs["response_format"] = {"type": "json_object"}
            try:
                response = client.chat.completions.create(**kwargs)
            except Exception as exc:
                # Not every model accepts response_format; a refusal there must
                # not cost the evaluation.
                # Two different refusals mean "cannot do JSON this way": the
                # model rejects response_format outright, or it accepted it and
                # produced nothing valid inside the token budget — a reasoning
                # model spends the budget on <think> and Groq answers
                # json_validate_failed with an empty failed_generation. Either
                # way a plain call still yields something the parser can work
                # on, which beats losing the evaluation.
                text = str(exc)
                recoverable = (
                    "response_format" in text
                    or "json_validate_failed" in text
                    or "Failed to validate JSON" in text
                    or "reasoning_effort" in text
                )
                if not json_mode or not recoverable:
                    raise
                # Drop only what the model objected to, so a model that dislikes
                # reasoning_effort still gets its JSON grammar.
                if "reasoning_effort" in text:
                    kwargs.pop("reasoning_effort", None)
                    response = client.chat.completions.create(**kwargs)
                    return (response.choices[0].message.content or "").strip()
                logger.info("Model %s rejected response_format; retrying plain",
                            self.model)
                kwargs.pop("response_format", None)
                response = client.chat.completions.create(**kwargs)
            return response.choices[0].message.content.strip()
        except Exception as e:
            err = str(e)
            # Auto-heal once if Groq rejects a leftover local-model id.
            if (
                self.model != DEFAULT_MODEL
                and ("model_not_found" in err or "does not exist" in err.lower())
            ):
                logger.warning(
                    "Groq model %r rejected (%s) — retrying with %s",
                    self.model,
                    err[:160],
                    DEFAULT_MODEL,
                )
                self.model = DEFAULT_MODEL
                try:
                    response = client.chat.completions.create(
                        model=self.model,
                        messages=messages,
                        max_tokens=max_tokens,
                    )
                    return response.choices[0].message.content.strip()
                except Exception as e2:
                    logger.error(f"Groq API error: {e2}")
                    raise RuntimeError(f"Groq request failed: {e2}") from e2
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
