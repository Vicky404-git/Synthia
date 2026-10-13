"""OpenAI-compatible chat provider (OpenAI, Groq, OpenRouter, ...).

Only the ``/chat/completions`` endpoint is used, so any provider exposing an
OpenAI-compatible API works by changing ``LLM_BASE_URL`` and ``LLM_MODEL``.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from ..config import Settings
from ..errors import ProviderError, RateLimitedError
from .base import LLMProvider, LLMResult


class OpenAICompatibleLLMProvider(LLMProvider):
    id = "openai"
    supports_structured = True

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._base_url = settings.llm_base_url.rstrip("/")
        self._api_key = settings.llm_api_key or ""
        self._timeout = settings.llm_timeout_seconds

    @property
    def model(self) -> str:
        return self._settings.llm_model

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code < 400:
            return
        if response.status_code == 401:
            raise ProviderError(
                "The LLM provider rejected the API key.",
                details={"provider": self.id, "upstream_status": 401},
                status_code=502,
            )
        if response.status_code == 429:
            raise RateLimitedError(
                "The LLM provider rate limit was reached.",
                details={"provider": self.id, "upstream_status": 429},
            )
        raise ProviderError(
            "The LLM provider returned an error.",
            details={
                "provider": self.id,
                "upstream_status": response.status_code,
                "upstream_message": _safe_text(response),
            },
        )

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int | None = None,
        temperature: float = 0.2,
    ) -> LLMResult:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens or self._settings.llm_max_tokens,
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers=self._headers(),
                    json=payload,
                )
        except httpx.TimeoutException as exc:
            raise ProviderError(
                "The LLM request timed out.", details={"provider": self.id}
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(
                "Could not reach the LLM provider.", details={"provider": self.id}
            ) from exc

        self._raise_for_status(response)
        data = response.json()
        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(
                "Unexpected response shape from the LLM provider.",
                details={"provider": self.id},
            ) from exc
        return LLMResult(
            text=text,
            provider=self.id,
            model=data.get("model", self.model),
            usage=data.get("usage"),
        )

    async def stream(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int | None = None,
        temperature: float = 0.2,
    ) -> AsyncIterator[str]:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens or self._settings.llm_max_tokens,
            "stream": True,
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                async with client.stream(
                    "POST",
                    f"{self._base_url}/chat/completions",
                    headers=self._headers(),
                    json=payload,
                ) as response:
                    if response.status_code >= 400:
                        await response.aread()
                        self._raise_for_status(response)
                    async for line in response.aiter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        chunk = line[len("data:") :].strip()
                        if chunk == "[DONE]":
                            break
                        try:
                            parsed = json.loads(chunk)
                            delta = parsed["choices"][0]["delta"].get("content")
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue
                        if delta:
                            yield delta
        except httpx.TimeoutException as exc:
            raise ProviderError(
                "The LLM stream timed out.", details={"provider": self.id}
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(
                "Could not reach the LLM provider.", details={"provider": self.id}
            ) from exc


def _safe_text(response: httpx.Response, limit: int = 300) -> str:
    try:
        return response.text[:limit]
    except Exception:  # pragma: no cover - defensive
        return ""
