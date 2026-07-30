"""
shortlistr LLM — Ollama adapter (local models, no API key required)

Requires:  Ollama running locally — https://ollama.com
           pip install requests (already in requirements.txt)
Models:    llama3 (default), mistral, gemma2, codellama, phi3, any Ollama model
URL:       http://localhost:11434 (default)
"""

import json
import logging
import requests
from .base import LLMProvider

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "llama3"
DEFAULT_URL   = "http://localhost:11434"


class OllamaProvider(LLMProvider):

    def __init__(self, model: str = DEFAULT_MODEL, base_url: str = DEFAULT_URL):
        self.model    = model or DEFAULT_MODEL
        self.base_url = base_url.rstrip("/")

    def complete(self, prompt: str, system: str = "", max_tokens: int = 1024) -> str:
        url     = f"{self.base_url}/api/generate"
        payload = {
            "model":  self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"num_predict": max_tokens},
        }
        if system:
            payload["system"] = system

        try:
            resp = requests.post(url, json=payload, timeout=120)
            resp.raise_for_status()
            data = resp.json()
            return data.get("response", "").strip()
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
