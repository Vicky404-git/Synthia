"""Placeholder STT provider used when no server-side recogniser is configured."""

from __future__ import annotations

from ..errors import ProviderNotConfiguredError
from .base import STTProvider, STTResult


class DisabledSTTProvider(STTProvider):
    id = "none"

    @property
    def available(self) -> bool:
        return False

    async def transcribe(
        self,
        audio: bytes,
        *,
        filename: str = "audio.webm",
        language: str | None = None,
    ) -> STTResult:
        raise ProviderNotConfiguredError(
            "No server-side speech-to-text provider is configured. "
            "Use browser speech recognition or typed input.",
            details={"stt_provider": self.id},
        )
