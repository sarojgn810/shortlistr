"""
shortlistr LLM — Abstract base class
All providers implement this interface.
"""


class LLMProvider:
    """Base class for all LLM providers."""

    def complete(self, prompt: str, system: str = "", max_tokens: int = 1024) -> str:
        """
        Send a prompt and return the text response.

        Args:
            prompt:     The user message / task
            system:     Optional system prompt
            max_tokens: Maximum tokens in the response

        Returns:
            Response text as a string.

        Raises:
            NotImplementedError if not overridden.
            RuntimeError on API / connection failure.
        """
        raise NotImplementedError(f"{self.__class__.__name__} must implement complete()")

    def is_available(self) -> bool:
        """
        Quick check that the provider is reachable / configured.
        Override in subclasses for provider-specific validation.
        """
        return True

    @classmethod
    def sdk_available(cls) -> bool:
        """Whether this provider's client library is importable. Override in
        providers that need a third-party SDK. Default True (e.g. Ollama uses
        `requests`, already a core dependency)."""
        return True

    @classmethod
    def install_hint(cls) -> str:
        """The pip command to install the missing SDK (empty when none is needed)."""
        return ""

    def __repr__(self):
        return f"<{self.__class__.__name__}>"
