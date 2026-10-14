"""Server-side speech-to-text provider abstraction.

The default recogniser is local Faster-Whisper (``STT_PROVIDER=faster-whisper``),
with hosted Whisper-compatible endpoints and a disabled provider as alternatives.
The browser Web Speech API remains a frontend-only fallback. Keeping the
recogniser behind this package means the API layer never needs to change when
the provider changes.
"""

from __future__ import annotations

from ..config import get_settings
from .base import STTProvider, STTResult
from .faster_whisper import (
    FasterWhisperSTTProvider,
    reset_faster_whisper_cache,
)
from .none import DisabledSTTProvider
from .openai_whisper import OpenAIWhisperSTTProvider


def _provider_id(value: str) -> str:
    return value.strip().lower().replace("_", "-")


def get_stt_provider() -> STTProvider:
    settings = get_settings()
    provider = _provider_id(settings.stt_provider)
    if provider in {"faster-whisper", "local"}:
        return FasterWhisperSTTProvider(settings)
    if provider == "openai" and settings.stt_api_key:
        return OpenAIWhisperSTTProvider(settings)
    return DisabledSTTProvider()


__all__ = [
    "STTProvider",
    "STTResult",
    "get_stt_provider",
    "reset_faster_whisper_cache",
]
