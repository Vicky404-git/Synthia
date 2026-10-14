"""Tests for the local Faster-Whisper STT provider.

Model loading and inference are mocked, so the suite never downloads a model
and never needs a GPU.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from app.config import Settings, get_settings
from app.errors import ProviderError
from app.stt import get_stt_provider, reset_faster_whisper_cache
from app.stt.faster_whisper import (
    FasterWhisperSTTProvider,
    LOCAL_MODEL_NAMES,
    normalize_language,
)
from app.stt.none import DisabledSTTProvider
from app.stt.openai_whisper import OpenAIWhisperSTTProvider


# --- fakes ------------------------------------------------------------------


class _Seg:
    def __init__(self, text: str) -> None:
        self.text = text


class _Info:
    def __init__(self, language: str = "en") -> None:
        self.language = language
        self.language_probability = 0.97
        self.duration = 1.0


class _Model:
    def __init__(
        self,
        segments: tuple[str, ...] = (" hello ", "world"),
        language: str = "en",
        raises: Exception | None = None,
        delay: float = 0.0,
    ) -> None:
        self._segments = segments
        self._language = language
        self._raises = raises
        self._delay = delay
        self.calls: list[dict] = []

    def transcribe(self, audio, **kwargs):  # noqa: ANN001
        self.calls.append(kwargs)
        if self._delay:
            time.sleep(self._delay)
        if self._raises is not None:
            raise self._raises
        return [_Seg(text) for text in self._segments], _Info(self._language)


def _patch_builder(monkeypatch, model):
    """Replace the real WhisperModel factory; return a call counter."""
    import app.stt.faster_whisper as fw

    calls = {"count": 0}

    def builder(_settings):  # noqa: ANN001
        calls["count"] += 1
        if isinstance(model, Exception):
            raise model
        return model

    monkeypatch.setattr(fw, "_build_model", builder)
    return calls


@pytest.fixture(autouse=True)
def _reset_state():
    get_settings.cache_clear()
    reset_faster_whisper_cache()
    yield
    get_settings.cache_clear()
    reset_faster_whisper_cache()


def _local_settings(**kwargs) -> Settings:
    return Settings(stt_provider="faster-whisper", **kwargs)


# --- provider selection -----------------------------------------------------


def test_provider_selection_by_configuration(monkeypatch):
    monkeypatch.setenv("STT_PROVIDER", "faster-whisper")
    get_settings.cache_clear()
    assert isinstance(get_stt_provider(), FasterWhisperSTTProvider)

    monkeypatch.setenv("STT_PROVIDER", "faster_whisper")
    get_settings.cache_clear()
    assert isinstance(get_stt_provider(), FasterWhisperSTTProvider)

    monkeypatch.setenv("STT_PROVIDER", "openai")
    monkeypatch.setenv("STT_API_KEY", "test-key")
    get_settings.cache_clear()
    assert isinstance(get_stt_provider(), OpenAIWhisperSTTProvider)

    monkeypatch.setenv("STT_PROVIDER", "none")
    get_settings.cache_clear()
    assert isinstance(get_stt_provider(), DisabledSTTProvider)


@pytest.mark.parametrize(
    ("value", "expected"),
    [("en-US", "en"), ("HI-IN", "hi"), ("fr", "fr"), ("pt_BR", "pt"), (None, None), ("", None)],
)
def test_normalize_language(value, expected):
    assert normalize_language(value) == expected


# --- transcription ----------------------------------------------------------


def test_successful_transcription_and_language(monkeypatch):
    model = _Model(segments=(" Hello ", "world. "), language="en")
    _patch_builder(monkeypatch, model)
    provider = FasterWhisperSTTProvider(_local_settings())

    result = asyncio.run(provider.transcribe(b"audio-bytes", language="en-US"))

    assert result.text == "Hello world."
    assert result.language == "en"
    assert result.provider == "faster-whisper"
    assert result.duration_ms is not None
    # "en-US" is normalised to the ISO-639-1 code Whisper expects.
    assert model.calls[0]["language"] == "en"


def test_detected_language_returned_when_not_requested(monkeypatch):
    _patch_builder(monkeypatch, _Model(language="de"))
    provider = FasterWhisperSTTProvider(_local_settings())
    result = asyncio.run(provider.transcribe(b"audio"))
    assert result.language == "de"


def test_model_is_loaded_once_and_reused(monkeypatch):
    calls = _patch_builder(monkeypatch, _Model())
    provider = FasterWhisperSTTProvider(_local_settings())
    asyncio.run(provider.transcribe(b"one"))
    asyncio.run(provider.transcribe(b"two"))
    assert calls["count"] == 1


# --- error handling ---------------------------------------------------------


def test_empty_audio_rejected(monkeypatch):
    _patch_builder(monkeypatch, _Model())
    provider = FasterWhisperSTTProvider(_local_settings())
    with pytest.raises(ProviderError):
        asyncio.run(provider.transcribe(b""))


def test_oversized_audio_rejected(monkeypatch):
    _patch_builder(monkeypatch, _Model())
    provider = FasterWhisperSTTProvider(_local_settings(stt_max_upload_bytes=8))
    with pytest.raises(ProviderError):
        asyncio.run(provider.transcribe(b"x" * 64))


def test_model_initialization_error_is_helpful(monkeypatch):
    _patch_builder(monkeypatch, RuntimeError("no internet"))
    provider = FasterWhisperSTTProvider(_local_settings())
    with pytest.raises(ProviderError) as excinfo:
        asyncio.run(provider.transcribe(b"audio"))
    assert "download" in str(excinfo.value).lower()


def test_inference_error_is_wrapped(monkeypatch):
    _patch_builder(monkeypatch, _Model(raises=ValueError("bad decode")))
    provider = FasterWhisperSTTProvider(_local_settings())
    with pytest.raises(ProviderError):
        asyncio.run(provider.transcribe(b"audio"))


def test_transcription_timeout(monkeypatch):
    _patch_builder(monkeypatch, _Model(delay=0.4))
    provider = FasterWhisperSTTProvider(_local_settings(stt_local_timeout_seconds=0.05))
    with pytest.raises(ProviderError):
        asyncio.run(provider.transcribe(b"audio"))


# --- hosted provider remains available -------------------------------------


class _FakeResponse:
    status_code = 200

    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def json(self) -> dict:
        return self._payload


class _FakeAsyncClient:
    last: dict = {}

    def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args) -> bool:  # noqa: ANN002
        return False

    async def post(self, url, **kwargs):  # noqa: ANN001
        _FakeAsyncClient.last = {"url": url, "kwargs": kwargs}
        return _FakeResponse({"text": " hosted hi ", "language": "en"})


def test_hosted_provider_still_works(monkeypatch):
    import app.stt.openai_whisper as ow

    monkeypatch.setattr(ow.httpx, "AsyncClient", _FakeAsyncClient)
    provider = OpenAIWhisperSTTProvider(
        Settings(stt_provider="openai", stt_api_key="key", stt_model="whisper-1")
    )
    result = asyncio.run(provider.transcribe(b"bytes", language="en-US"))
    assert result.text == "hosted hi"
    assert result.provider == "openai-whisper"
    assert _FakeAsyncClient.last["url"].endswith("/audio/transcriptions")


def test_hosted_model_falls_back_from_local_default():
    provider = OpenAIWhisperSTTProvider(
        Settings(stt_provider="openai", stt_api_key="key", stt_model="base")
    )
    assert "base" in LOCAL_MODEL_NAMES
    assert provider._model == "whisper-1"


# --- HTTP endpoint ----------------------------------------------------------


def test_endpoint_uses_faster_whisper(make_client, monkeypatch):
    _patch_builder(monkeypatch, _Model(segments=("hello", "world")))
    client = make_client(STT_PROVIDER="faster-whisper")
    response = client.post(
        "/api/stt/transcribe",
        files={"file": ("audio.webm", b"raw-audio", "audio/webm")},
        data={"language": "en-US"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["text"] == "hello world"
    assert body["provider"] == "faster-whisper"
    assert body["language"] == "en"


def test_endpoint_reports_local_stt_ready(make_client):
    client = make_client(STT_PROVIDER="faster-whisper")
    ready = client.get("/ready").json()
    stt = next(dep for dep in ready["dependencies"] if dep["name"] == "stt")
    assert stt["ready"] is True
    assert "faster-whisper" in stt["detail"]


def test_endpoint_empty_upload_errors(make_client, monkeypatch):
    _patch_builder(monkeypatch, _Model())
    client = make_client(STT_PROVIDER="faster-whisper")
    response = client.post("/api/stt/transcribe", files={"file": ("a.webm", b"")})
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "provider_error"


def test_endpoint_requires_auth_when_token_set(make_client, monkeypatch):
    _patch_builder(monkeypatch, _Model())
    client = make_client(STT_PROVIDER="faster-whisper", API_AUTH_TOKEN="secret")
    denied = client.post("/api/stt/transcribe", files={"file": ("a.webm", b"x")})
    assert denied.status_code == 401
    allowed = client.post(
        "/api/stt/transcribe",
        headers={"Authorization": "Bearer secret"},
        files={"file": ("a.webm", b"x")},
    )
    assert allowed.status_code == 200
