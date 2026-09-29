"""Google Gemini generateContent provider (REST)."""

from __future__ import annotations

import httpx

from app.core.config import settings
from app.core.exceptions import ServiceUnavailableError
from app.core.logging import get_logger
from app.rag.generation.llm import LLMProvider

logger = get_logger(__name__)

GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiProvider(LLMProvider):
    name = "gemini"

    def _url(self) -> str:
        return f"{GEMINI_ENDPOINT}/{settings.LLM_MODEL}:generateContent"

    def _payload(self, system: str, user: str) -> dict:
        return {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                "temperature": settings.LLM_TEMPERATURE,
                "maxOutputTokens": settings.LLM_MAX_TOKENS,
            },
        }

    async def complete(self, system: str, user: str) -> str:
        if not settings.LLM_API_KEY:
            raise ServiceUnavailableError(
                "LLM_API_KEY is not configured for the 'gemini' provider."
            )
        params = {"key": settings.LLM_API_KEY}
        try:
            async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    self._url(), params=params, json=self._payload(system, user)
                )
                response.raise_for_status()
                data = response.json()
                candidates = data.get("candidates", [])
                if not candidates:
                    return ""
                parts = candidates[0].get("content", {}).get("parts", [])
                return "".join(part.get("text", "") for part in parts)
        except httpx.HTTPStatusError as exc:
            logger.error("Gemini API error: %s %s", exc.response.status_code, exc.response.text[:500])
            raise ServiceUnavailableError(
                f"Gemini API returned HTTP {exc.response.status_code}."
            ) from exc
        except httpx.RequestError as exc:
            logger.error("Gemini request failed: %s", exc)
            raise ServiceUnavailableError(f"Could not reach Gemini: {exc}") from exc