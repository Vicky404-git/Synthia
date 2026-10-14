"""Optional voice-command endpoints (AWS Lex V2 or simulated).

These routes expose a small, stable contract regardless of the provider behind
it. Recognition results are always labelled ``live`` or ``simulated`` so a demo
response is never mistaken for a real AWS one. Lex-derived intents and slots
are treated as untrusted and validated in the provider layer.
"""

from __future__ import annotations

import uuid

from anyio import to_thread
from fastapi import APIRouter, File, Form, Request, UploadFile

from ..auth import client_key, ensure_authorized, get_rate_limiter
from ..config import get_settings
from ..errors import ProviderNotConfiguredError, ValidationError
from ..lex import LexIntentResult, get_lex_provider, resolve_session_id
from ..schemas import (
    LexCommandMode,
    LexCommandRequest,
    LexCommandResponse,
    LexStatusResponse,
    ProviderStatus,
)
from ..stt import get_stt_provider

router = APIRouter(prefix="/api/lex", tags=["lex"])

_PROVIDER_DISABLED = "No command provider is available."


def _mode_for(result: LexIntentResult) -> LexCommandMode:
    return LexCommandMode.simulated if result.simulated else LexCommandMode.live


def _to_response(result: LexIntentResult) -> LexCommandResponse:
    return LexCommandResponse(
        id=uuid.uuid4().hex,
        transcript=result.transcript,
        intent=result.intent,
        slots=result.slots,
        fulfillment_message=result.fulfillment_message,
        mode=_mode_for(result),
        provider=result.provider,
        session_id=result.session_id,
        latency_ms=result.latency_ms,
        warnings=result.warnings,
    )


@router.get("/status", response_model=LexStatusResponse)
async def lex_status() -> LexStatusResponse:
    settings = get_settings()
    provider = get_lex_provider()
    health = provider.health()
    if health.status == ProviderStatus.connected:
        mode = LexCommandMode.live
    elif health.status == ProviderStatus.demo:
        mode = LexCommandMode.simulated
    else:
        mode = LexCommandMode.disabled
    return LexStatusResponse(
        enabled=settings.lex_enabled,
        configured=settings.lex_configured,
        available=provider.available,
        mode=mode,
        provider=provider.id,
        detail=health.detail,
        setup_hint=health.setup_hint,
    )


@router.post("/command", response_model=LexCommandResponse)
async def lex_command(req: LexCommandRequest, request: Request) -> LexCommandResponse:
    settings = get_settings()
    get_rate_limiter().check(client_key(request))
    ensure_authorized(request.headers.get("authorization"))

    provider = get_lex_provider()
    if not provider.available:
        raise ProviderNotConfiguredError(
            _PROVIDER_DISABLED,
            details={"lex_provider": provider.id, "hint": provider.health().detail},
        )

    session_id = resolve_session_id(req.session_id, settings.lex_session_id_prefix)
    result = await to_thread.run_sync(
        lambda: provider.recognize_text(req.text, session_id=session_id)
    )
    return _to_response(result)


@router.post("/voice", response_model=LexCommandResponse)
async def lex_voice(
    request: Request,
    file: UploadFile = File(...),
    transcript: str | None = Form(default=None),
    session_id: str | None = Form(default=None),
    content_type: str | None = Form(default=None),
    language: str | None = Form(default=None),
) -> LexCommandResponse:
    settings = get_settings()
    get_rate_limiter().check(client_key(request))
    ensure_authorized(request.headers.get("authorization"))

    provider = get_lex_provider()
    if not provider.available:
        raise ProviderNotConfiguredError(
            _PROVIDER_DISABLED,
            details={"lex_provider": provider.id},
        )

    resolved_session = resolve_session_id(
        session_id, settings.lex_session_id_prefix
    )
    audio = await file.read()
    if len(audio) > settings.stt_max_upload_bytes:
        raise ValidationError(
            "Audio upload is too large.",
            details={"max_bytes": settings.stt_max_upload_bytes},
        )
    detected_type = content_type or file.content_type or "audio/l16"

    # 1. Prefer audio directly only when explicitly enabled for a capable
    #    provider and the caller confirms raw 16 kHz mono PCM.
    if settings.lex_use_recognize_utterance:
        try:
            result = await to_thread.run_sync(
                lambda: provider.recognize_utterance(
                    audio,
                    session_id=resolved_session,
                    content_type=detected_type,
                    language=language,
                )
            )
            return _to_response(result)
        except NotImplementedError:
            pass  # fall through to the STT -> RecognizeText path

    # 2. Otherwise keep audio capture and speech-to-text separate: transcribe
    #    with the configured STT provider, then send the transcript to Lex.
    text = (transcript or "").strip()
    if not text:
        stt = get_stt_provider()
        if not stt.available:
            raise ProviderNotConfiguredError(
                "No transcript was supplied and no server-side speech-to-text "
                "provider is configured.",
                details={"stt_provider": stt.id},
            )
        stt_result = await stt.transcribe(
            audio, filename=file.filename or "audio.webm", language=language
        )
        text = stt_result.text.strip()
        if not text:
            raise ValidationError(
                "Speech-to-text returned an empty transcript.",
                details={"stt_provider": stt.id},
            )

    result = await to_thread.run_sync(
        lambda: provider.recognize_text(text, session_id=resolved_session)
    )
    return _to_response(result)
