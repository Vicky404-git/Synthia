"""Base types for speech-to-text providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class STTResult:
    text: str
    provider: str
    language: str | None = None
    # Only populated when the provider genuinely returns a confidence score.
    confidence: float | None = None
    duration_ms: int | None = None


class STTProvider(ABC):
    id: str = "base"

    @property
    @abstractmethod
    def available(self) -> bool: ...

    @abstractmethod
    async def transcribe(
        self,
        audio: bytes,
        *,
        filename: str = "audio.webm",
        language: str | None = None,
    ) -> STTResult: ...
