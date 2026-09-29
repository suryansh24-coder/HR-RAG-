"""OpenAI-compatible chat completions provider."""

from __future__ import annotations

import time

import httpx

from app.core.config import settings
from app.core.exceptions import ServiceUnavailableError
from app.core.logging import get_logger
from app.rag.generation.llm import LLMProvider

logger = get_logger(__name__)


class OpenAICompatibleProvider(LLMProvider):
    name = "openai"

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {settings.LLM_API_KEY}",
            "Content-Type": "application/json",
        }

    def _payload(self, system: str, user: str) -> dict:
        return {
            "model": settings.LLM_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": settings.LLM_TEMPERATURE,
            "max_tokens": settings.LLM_MAX_TOKENS,
        }

    async def complete(self, system: str, user: str) -> str:
        if not settings.LLM_API_KEY:
            raise ServiceUnavailableError(
                "LLM_API_KEY is not configured for the 'openai' provider."
            )
        url = f"{settings.LLM_BASE_URL.rstrip('/')}/chat/completions"
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT_SECONDS) as client:
                response = await client.post(url, headers=self._headers(), json=self._payload(system, user))
                response.raise_for_status()
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                return content or ""
        except httpx.HTTPStatusError as exc:
            logger.error(
                "OpenAI-compatible endpoint error: %s body=%s",
                exc.response.status_code,
                exc.response.text[:500],
            )
            raise ServiceUnavailableError(
                f"LLM endpoint returned HTTP {exc.response.status_code}."
            ) from exc
        except httpx.RequestError as exc:
            logger.error("OpenAI-compatible request failed: %s", exc)
            raise ServiceUnavailableError(f"Could not reach the LLM endpoint: {exc}") from exc
        finally:
            logger.debug("openai.call latency=%.0fms", (time.perf_counter() - started) * 1000)