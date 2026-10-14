"""Local Faster-Whisper speech-to-text provider.

Runs entirely on the Synthia backend host using CTranslate2 with CPU/INT8 by
default, so no GPU or external API is required. The Whisper model is loaded
lazily on the first transcription and cached for the process lifetime; it is
never downloaded during a Docker image build.

Audio never leaves the backend host, but it *is* uploaded from the browser to
the backend, so the UI must make that clear. Raw audio is never logged.
"""

from __future__ import annotations

import asyncio
import importlib.util
import logging
import threading
import time
from io import BytesIO
from typing import Any

import anyio

from ..config import Settings
from ..errors import ProviderError
from .base import STTProvider, STTResult

logger = logging.getLogger(__name__)

# Process-wide model cache. Keyed by the settings that affect the loaded model
# so the model is reused across requests and never reloaded per transcription.
_MODEL_CACHE: dict[tuple[Any, ...], Any] = {}
_MODEL_LOCK = threading.Lock()

# Model names understood by faster-whisper. Used to keep the hosted provider
# sane if it is enabled without an explicit hosted model name.
LOCAL_MODEL_NAMES = {
    "tiny",
    "tiny.en",
    "base",
    "base.en",
    "small",
    "small.en",
    "medium",
    "medium.en",
    "large",
    "large-v1",
    "large-v2",
    "large-v3",
    "turbo",
    "distil-small.en",
    "distil-medium.en",
    "distil-large-v2",
    "distil-large-v3",
}


def reset_faster_whisper_cache() -> None:
    """Drop the cached model. Used by tests and safe to call at runtime."""
    with _MODEL_LOCK:
        _MODEL_CACHE.clear()


def _cache_key(settings: Settings) -> tuple[Any, ...]:
    return (
        settings.stt_model,
        settings.stt_device,
        settings.stt_compute_type,
        settings.stt_cpu_threads,
        settings.stt_num_workers,
        settings.stt_cache_dir or "",
    )


def _build_model(settings: Settings) -> Any:
    """Construct a real ``WhisperModel``. Patched in unit tests."""
    from faster_whisper import WhisperModel

    kwargs: dict[str, Any] = {
        "device": settings.stt_device,
        "compute_type": settings.stt_compute_type,
        "cpu_threads": settings.stt_cpu_threads,
        "num_workers": settings.stt_num_workers,
    }
    if settings.stt_cache_dir:
        kwargs["download_root"] = settings.stt_cache_dir
    return WhisperModel(settings.stt_model, **kwargs)


def get_whisper_model(settings: Settings) -> Any:
    """Return a cached Whisper model, loading it once on first use."""
    key = _cache_key(settings)
    with _MODEL_LOCK:
        cached = _MODEL_CACHE.get(key)
        if cached is not None:
            return cached
        try:
            model = _build_model(settings)
        except Exception as exc:  # noqa: BLE001 - surface a safe, useful message
            logger.warning(
                "Failed to load faster-whisper model %r: %s",
                settings.stt_model,
                type(exc).__name__,
            )
            raise ProviderError(
                "Could not load the local speech model. The first run needs "
                "internet access to download the model; check the network "
                "connection, STT_MODEL and STT_CACHE_DIR, then try again.",
                details={
                    "provider": "faster-whisper",
                    "model": settings.stt_model,
                    "cache_dir": settings.stt_cache_dir or "(default)",
                },
            ) from exc
        _MODEL_CACHE[key] = model
        return model


def normalize_language(language: str | None) -> str | None:
    """Map a UI locale like ``en-US`` to the ISO-639-1 code Whisper expects."""
    if not language:
        return None
    return language.strip().split("-")[0].split("_")[0].lower() or None


class FasterWhisperSTTProvider(STTProvider):
    id = "faster-whisper"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._max_bytes = settings.stt_max_upload_bytes
        self._timeout = settings.stt_local_timeout_seconds
        self._beam_size = settings.stt_beam_size
        self._vad_filter = settings.stt_vad_filter
        self.model = settings.stt_model

    @property
    def available(self) -> bool:
        return importlib.util.find_spec("faster_whisper") is not None

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
        if not self.available:
            raise ProviderError(
                "The faster-whisper package is not installed on the backend.",
                details={"provider": self.id},
            )

        normalized = normalize_language(language)
        started = time.perf_counter()
        try:
            model = await asyncio.wait_for(
                anyio.to_thread.run_sync(get_whisper_model, self._settings),
                timeout=self._timeout,
            )
            segments, info = await asyncio.wait_for(
                anyio.to_thread.run_sync(self._run, model, audio, normalized),
                timeout=self._timeout,
            )
        except ProviderError:
            raise
        except (asyncio.TimeoutError, TimeoutError) as exc:
            raise ProviderError(
                "Local transcription timed out. Try a shorter clip or a smaller "
                "STT_MODEL.",
                details={"provider": self.id, "timeout_seconds": self._timeout},
            ) from exc
        except Exception as exc:  # noqa: BLE001 - decoding/inference failures
            logger.warning(
                "faster-whisper transcription failed: %s", type(exc).__name__
            )
            raise ProviderError(
                "The audio could not be transcribed. It may be empty, corrupt, "
                "or in a format the decoder does not support.",
                details={"provider": self.id},
            ) from exc

        text = " ".join(segment.text.strip() for segment in segments).strip()
        detected = getattr(info, "language", None)
        duration_ms = int((time.perf_counter() - started) * 1000)
        return STTResult(
            text=text,
            provider=self.id,
            language=detected or normalized,
            confidence=None,
            duration_ms=duration_ms,
        )

    def _run(self, model: Any, audio: bytes, language: str | None) -> tuple[list, Any]:
        segments, info = model.transcribe(
            BytesIO(audio),
            language=language,
            beam_size=self._beam_size,
            vad_filter=self._vad_filter,
            condition_on_previous_text=False,
        )
        return list(segments), info
