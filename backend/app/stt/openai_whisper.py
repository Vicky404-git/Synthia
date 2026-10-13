"""OpenAI-compatible Whisper transcription provider.

Audio is forwarded to a hosted API and is not retained by Synthia. The caller
must explicitly opt into online transcription; this provider never runs
automatically.
"""

from __future__ import annotations

import time

import httpx

from ..config import Settings
from ..errors import ProviderError, RateLimitedError
from .base import STTProvider, STTResult


class OpenAIWhisperSTTProvider(STTProvider):
    id = "openai-whisper"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._base_url = settings.stt_base_url.rstrip("/")
        self._api_key = settings.stt_api_key or ""
        self._model = settings.stt_model
        self._timeout = settings.stt_timeout_seconds
        self._max_bytes = settings.stt_max_upload_bytes

    @property
    def available(self) -> bool:
        return True

    async def transcribe(
        self,
        audio: bytes,
        *,
        filename: str = "audio.webm",
        language: str | None = None,
    ) -> STTResult:
        if not audio:
            raise ProviderError("Empty audio payload.", details={"provider": self.id})
        if len(audio) > self._max_bytes:
            raise ProviderError(
                "Audio upload exceeds the configured size limit.",
                details={"provider": self.id, "max_bytes": self._max_bytes},
            )
        data = {"model": self._model}
        if language:
            data["language"] = language
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._base_url}/audio/transcriptions",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    data=data,
                    files={"file": (filename, audio, "application/octet-stream")},
                )
        except httpx.TimeoutException as exc:
            raise ProviderError(
                "The speech-to-text request timed out.",
                details={"provider": self.id},
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(
                "Could not reach the speech-to-text provider.",
                details={"provider": self.id},
            ) from exc

        if response.status_code == 401:
            raise ProviderError(
                "The speech-to-text provider rejected the API key.",
                details={"provider": self.id, "upstream_status": 401},
            )
        if response.status_code == 429:
            raise RateLimitedError(
                "The speech-to-text provider rate limit was reached.",
                details={"provider": self.id, "upstream_status": 429},
            )
        if response.status_code >= 400:
            raise ProviderError(
                "The speech-to-text provider returned an error.",
                details={"provider": self.id, "upstream_status": response.status_code},
            )

        payload = response.json()
        duration_ms = int((time.perf_counter() - started) * 1000)
        return STTResult(
            text=(payload.get("text") or "").strip(),
            provider=self.id,
            language=payload.get("language") or language,
            confidence=None,
            duration_ms=duration_ms,
        )
