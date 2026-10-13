"""Transcription history and optional server-side speech-to-text.

The frontend owns V1 history in localStorage. These endpoints exist for
server-side recording and to expose an optional hosted STT provider. They are
protected by the bearer token whenever ``API_AUTH_TOKEN`` is configured.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile

from ..auth import require_auth
from ..config import get_settings
from ..errors import ProviderNotConfiguredError, ValidationError
from ..schemas import (
    TranscriptionEvent,
    TranscriptionEventCreate,
    TranscriptionEventList,
)
from ..stt import get_stt_provider
from ..store import get_transcription_store

router = APIRouter(prefix="/api", tags=["transcriptions"])

_PERSISTENCE = "in-memory (ephemeral)"
_NOTE = (
    "Server-side history is intentionally ephemeral and non-authoritative. "
    "The browser keeps the durable V1 history in localStorage."
)


@router.post(
    "/transcriptions",
    response_model=TranscriptionEvent,
    dependencies=[Depends(require_auth)],
)
async def create_transcription(payload: TranscriptionEventCreate) -> TranscriptionEvent:
    return get_transcription_store().create(payload)


@router.get(
    "/transcriptions",
    response_model=TranscriptionEventList,
    dependencies=[Depends(require_auth)],
)
async def list_transcriptions() -> TranscriptionEventList:
    events = get_transcription_store().list()
    return TranscriptionEventList(
        events=events, count=len(events), persistence=_PERSISTENCE, note=_NOTE
    )


@router.get(
    "/transcriptions/{event_id}",
    response_model=TranscriptionEvent,
    dependencies=[Depends(require_auth)],
)
async def get_transcription(event_id: str) -> TranscriptionEvent:
    event = get_transcription_store().get(event_id)
    if event is None:
        raise ValidationError(
            "No transcription event with that id.",
            details={"event_id": event_id},
            status_code=404,
        )
    return event


@router.delete(
    "/transcriptions",
    dependencies=[Depends(require_auth)],
)
async def clear_transcriptions() -> dict:
    removed = get_transcription_store().clear()
    return {"cleared": removed}


@router.post(
    "/stt/transcribe",
    dependencies=[Depends(require_auth)],
)
async def transcribe_audio(
    file: UploadFile = File(...),
    language: str | None = Form(default=None),
) -> dict:
    settings = get_settings()
    provider = get_stt_provider()
    if not provider.available:
        raise ProviderNotConfiguredError(
            "No server-side speech-to-text provider is configured. "
            "Browser speech recognition remains available.",
            details={"stt_provider": provider.id},
        )
    audio = await file.read()
    if len(audio) > settings.stt_max_upload_bytes:
        raise ValidationError(
            "Audio upload is too large.",
            details={"max_bytes": settings.stt_max_upload_bytes},
        )
    result = await provider.transcribe(
        audio, filename=file.filename or "audio.webm", language=language
    )
    return {
        "text": result.text,
        "provider": result.provider,
        "language": result.language,
        "confidence": result.confidence,
        "duration_ms": result.duration_ms,
    }
