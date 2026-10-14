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
from .providers import chat_completions_url


class OpenAICompatibleLLMProvider(LLMProvider):
    supports_structured = True

    def __init__(
        self,
        settings: Settings,
        *,
        provider_id: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        timeout: float | None = None,
        max_tokens: int | None = None,
    ) -> None:
        self._settings = settings
        # The reportable provider id reflects what actually served the request,
        # not a hardcoded "openai" (BYOK requests select any registered id).
        self.id = provider_id or settings.llm_provider or "openai"
        self._base_url = base_url or settings.llm_base_url
        self._model = model or settings.llm_model
        self._api_key = (api_key if api_key is not None else settings.llm_api_key) or ""
        self._timeout = timeout if timeout is not None else settings.llm_timeout_seconds
        self._max_tokens = (
            max_tokens if max_tokens is not None else settings.llm_max_tokens
        )

    @property
    def model(self) -> str:
        return self._model

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
                # Redact defensively in case an upstream echoes credentials.
                "upstream_message": redact(_safe_text(response), self._api_key),
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
            "max_tokens": max_tokens or self._max_tokens,
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    chat_completions_url(self._base_url),
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
            "max_tokens": max_tokens or self._max_tokens,
            "stream": True,
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                async with client.stream(
                    "POST",
                    chat_completions_url(self._base_url),
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


def redact(text: str, secret: str) -> str:
    """Replace any occurrence of ``secret`` so it can never surface in errors."""
    if secret and secret in text:
        return text.replace(secret, "***")
    return text
