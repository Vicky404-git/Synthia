"""Server-side speech-to-text provider abstraction.

V1 uses the browser Web Speech API as the primary recogniser. This package
exists so a hosted STT service (or a future custom model) can be plugged in
without touching the API layer.
"""

from __future__ import annotations

from ..config import get_settings
from .base import STTProvider, STTResult
from .none import DisabledSTTProvider
from .openai_whisper import OpenAIWhisperSTTProvider


def get_stt_provider() -> STTProvider:
    settings = get_settings()
    if settings.stt_provider == "openai" and settings.stt_api_key:
        return OpenAIWhisperSTTProvider(settings)
    return DisabledSTTProvider()


__all__ = ["STTProvider", "STTResult", "get_stt_provider"]
