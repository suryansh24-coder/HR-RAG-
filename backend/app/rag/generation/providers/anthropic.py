"""Anthropic Claude Messages API provider."""

from __future__ import annotations

import httpx

from app.core.config import settings
from app.core.exceptions import ServiceUnavailableError
from app.core.logging import get_logger
from app.rag.generation.llm import LLMProvider

logger = get_logger(__name__)

CLAUDE_ENDPOINT = "https://api.anthropic.com/v1/messages"
CLAUDE_VERSION = "2023-06-01"


class AnthropicProvider(LLMProvider):
    name = "claude"

    def _headers(self) -> dict:
        return {
            "x-api-key": settings.LLM_API_KEY,
            "anthropic-version": CLAUDE_VERSION,
            "content-type": "application/json",
        }

    def _payload(self, system: str, user: str) -> dict:
        return {
            "model": settings.LLM_MODEL,
            "max_tokens": settings.LLM_MAX_TOKENS,
            "temperature": settings.LLM_TEMPERATURE,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }

    async def complete(self, system: str, user: str) -> str:
        if not settings.LLM_API_KEY:
            raise ServiceUnavailableError(
                "LLM_API_KEY is not configured for the 'claude' provider."
            )
        try:
            async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    CLAUDE_ENDPOINT,
                    headers=self._headers(),
                    json=self._payload(system, user),
                )
                response.raise_for_status()
                data = response.json()
                return "".join(
                    block.get("text", "")
                    for block in data.get("content", [])
                    if block.get("type") == "text"
                )
        except httpx.HTTPStatusError as exc:
            logger.error("Claude API error: %s %s", exc.response.status_code, exc.response.text[:500])
            raise ServiceUnavailableError(
                f"Claude API returned HTTP {exc.response.status_code}."
            ) from exc
        except httpx.RequestError as exc:
            logger.error("Claude request failed: %s", exc)
            raise ServiceUnavailableError(f"Could not reach Claude: {exc}") from exc