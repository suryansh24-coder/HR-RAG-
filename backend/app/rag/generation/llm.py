"""LLM provider abstraction.

Providers are swappable at runtime via ``LLM_PROVIDER``:

* ``openai`` — any OpenAI-compatible ``/chat/completions`` endpoint
  (OpenAI, Azure OpenAI, Ollama, vLLM, LM Studio, Groq, Together, ...)
* ``claude`` — Anthropic Messages API
* ``gemini`` — Google Gemini generateContent API
* ``extractive`` — offline deterministic responder used for tests/CI/demo. It
  answers strictly from retrieved context (never hallucinates). Rejected with a
  clear error when ``APP_ENV=production``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.core.config import settings
from app.core.exceptions import ProviderConfigurationError, ServiceUnavailableError


class LLMProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def complete(self, system: str, user: str) -> str:
        """Return the generated assistant text for the given messages."""


class LLMResult:
    __slots__ = ("text", "latency_ms", "provider", "model", "error")

    def __init__(
        self,
        text: str = "",
        provider: str = "",
        model: str = "",
        latency_ms: float = 0.0,
        error: str | None = None,
    ) -> None:
        self.text = text
        self.provider = provider
        self.model = model
        self.latency_ms = latency_ms
        self.error = error


def provider_factory() -> LLMProvider:
    provider = (settings.LLM_PROVIDER or "").strip().lower()

    if settings.is_production and provider == "extractive":
        raise ProviderConfigurationError(
            "The 'extractive' LLM provider is not allowed in production. "
            "Set LLM_PROVIDER to openai, claude or gemini."
        )

    if provider == "openai":
        from app.rag.generation.providers.openai_compatible import OpenAICompatibleProvider

        return OpenAICompatibleProvider()
    if provider == "claude":
        from app.rag.generation.providers.anthropic import AnthropicProvider

        return AnthropicProvider()
    if provider == "gemini":
        from app.rag.generation.providers.gemini import GeminiProvider

        return GeminiProvider()
    if provider == "extractive":
        from app.rag.generation.providers.extractive import ExtractiveProvider

        return ExtractiveProvider()

    raise ProviderConfigurationError(
        f"Unknown LLM_PROVIDER '{settings.LLM_PROVIDER}'. "
        "Use one of: openai, claude, gemini, extractive."
    )