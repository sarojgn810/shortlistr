"""
shortlistr LLM — Ollama adapter (local models, no API key required)

Requires:  Ollama running locally — https://ollama.com
           pip install requests (already in requirements.txt)
Models:    llama3 (default), mistral, gemma2, codellama, phi3, any Ollama model
URL:       http://localhost:11434 (default)
"""

import json
import logging
import re
import requests
from .base import LLMProvider

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "llama3"
DEFAULT_URL   = "http://localhost:11434"


_THINK_RE = re.compile(r"<think>.*?</think>", re.S | re.I)


def _strip_reasoning(text: str) -> str:
    """Drop <think> blocks. Reasoning models (qwen3, deepseek-r1) emit them
    before the answer, and they are not part of it."""
    return _THINK_RE.sub("", text or "")


class OllamaProvider(LLMProvider):

    def __init__(self, model: str = DEFAULT_MODEL, base_url: str = DEFAULT_URL):
        self.model    = model or DEFAULT_MODEL
        self.base_url = base_url.rstrip("/")

    def complete(self, prompt: str, system: str = "", max_tokens: int = 1024,
                 json_mode: bool = False) -> str:
        url     = f"{self.base_url}/api/generate"
        payload = {
            "model":  self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"num_predict": max_tokens},
        }
        if json_mode:
            # Same trap as the hosted qwen3: a reasoning model narrates before
            # it answers and can spend the whole budget doing it. Ollama takes
            # `think` from 0.9 onward; older builds reject the field, so the
            # request is retried without it rather than failing the evaluation.
            payload["think"] = False
            # Ollama constrains sampling to valid JSON. Without it a small model
            # answers the evaluation prompt in prose and the parser gets "No
            # JSON object in LLM response" — measured on qwen3:0.6b, which is
            # what an 18GB laptop picks. The grammar is what makes a small local
            # model usable here at all.
            payload["format"] = "json"
        if system:
            payload["system"] = system

        try:
            resp = requests.post(url, json=payload, timeout=120)
            if resp.status_code == 400 and "think" in payload:
                payload.pop("think", None)
                resp = requests.post(url, json=payload, timeout=120)
            resp.raise_for_status()
            data = resp.json()
            return _strip_reasoning(data.get("response", "")).strip()
        except requests.ConnectionError:
            raise RuntimeError(
                f"Cannot connect to Ollama at {self.base_url}. "
                "Is Ollama running? Start it with: ollama serve"
            )
        except Exception as e:
            logger.error(f"Ollama error: {e}")
            raise RuntimeError(f"Ollama request failed: {e}") from e

    def is_available(self) -> bool:
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False

    def __repr__(self):
        return f"<OllamaProvider model={self.model} url={self.base_url}>"
