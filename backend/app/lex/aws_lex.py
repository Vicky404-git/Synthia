"""AWS Lex V2 Runtime adapter.

Uses boto3's standard credential chain (IAM role, shared config, or
environment variables) — credentials are never hardcoded or logged. It calls
``RecognizeText`` for transcripts and, when enabled, ``RecognizeUtterance`` for
audio.

Scope note: Synthia does not reimplement Lex fulfilment. The bot is expected
to have its own Lambda code hook; the messages returned here are whatever the
bot's fulfilment produced. Synthia only parses the stable fields it needs.
"""

from __future__ import annotations

import time
from typing import Any

from ..config import Settings
from ..errors import ProviderError, ProviderNotConfiguredError
from ..schemas import ProviderStatus
from .base import LexHealth, LexIntentResult, LexProvider
from .policy import normalize_intent, sanitize_slots

# Lex RecognizeUtterance accepts raw PCM (and a few container formats). We only
# forward an allowlisted content type so an untrusted caller cannot inject
# arbitrary header content.
_ALLOWED_CONTENT_TYPES = ("audio/l16", "audio/pcm", "audio/wav", "audio/x-wav")
_DEFAULT_CONTENT_TYPE = "audio/l16; rate=16000; channels=1"


class AWSLexProvider(LexProvider):
    id = "aws-lex"
    simulated = False

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    # -- health ------------------------------------------------------------

    @property
    def available(self) -> bool:
        return self._settings.lex_configured and self._credentials_available()[0]

    def _credentials_available(self) -> tuple[bool, str]:
        try:
            import boto3  # noqa: PLC0415
        except ImportError:
            return False, "boto3 is not installed."
        try:
            credentials = boto3.Session().get_credentials()
        except Exception:  # pragma: no cover - defensive
            return False, "Could not initialise a boto3 session."
        if credentials is None:
            return False, "No AWS credentials found in the environment or chain."
        # Never return the credential value, only how it was resolved.
        return True, f"Credentials resolved via {getattr(credentials, 'method', 'unknown')}."

    def health(self) -> LexHealth:
        if not self._settings.lex_enabled:
            return LexHealth(
                status=ProviderStatus.disabled,
                detail="AWS Lex integration is disabled (set LEX_ENABLED=true).",
                provider=self.id,
                simulated=False,
                setup_hint="Set LEX_ENABLED=true, LEX_BOT_ID and LEX_BOT_ALIAS_ID.",
            )
        if not self._settings.lex_bot_id or not self._settings.lex_bot_alias_id:
            return LexHealth(
                status=ProviderStatus.unconfigured,
                detail="LEX_BOT_ID and LEX_BOT_ALIAS_ID are required.",
                provider=self.id,
                simulated=False,
                setup_hint=(
                    "Create a Lex V2 bot, alias it, then set LEX_BOT_ID and "
                    "LEX_BOT_ALIAS_ID (use TSTALIASID for the test alias)."
                ),
            )
        available, detail = self._credentials_available()
        if not available:
            return LexHealth(
                status=ProviderStatus.unconfigured,
                detail=detail,
                provider=self.id,
                simulated=False,
                setup_hint=(
                    "Provide AWS credentials via the standard chain, or run on "
                    "a role with lex:RecognizeText permission."
                ),
            )
        return LexHealth(
            status=ProviderStatus.connected,
            detail=f"{detail} Live AWS Lex V2 responses.",
            provider=self.id,
            simulated=False,
        )

    # -- client ------------------------------------------------------------

    def _client(self) -> Any:
        try:
            import boto3  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover - depends on env
            raise ProviderNotConfiguredError(
                "boto3 is required for the AWS Lex integration.",
                details={"provider": self.id},
            ) from exc
        if not self._settings.lex_enabled:
            raise ProviderNotConfiguredError(
                "AWS Lex integration is disabled.",
                details={"provider": self.id, "hint": "set LEX_ENABLED=true"},
            )
        if not self._settings.lex_bot_id or not self._settings.lex_bot_alias_id:
            raise ProviderNotConfiguredError(
                "LEX_BOT_ID and LEX_BOT_ALIAS_ID must be set.",
                details={"provider": self.id},
            )
        kwargs: dict[str, Any] = {
            "region_name": self._settings.aws_default_region,
        }
        if self._settings.aws_access_key_id:
            kwargs["aws_access_key_id"] = self._settings.aws_access_key_id
        if self._settings.aws_secret_access_key:
            kwargs["aws_secret_access_key"] = self._settings.aws_secret_access_key
        if self._settings.aws_session_token:
            kwargs["aws_session_token"] = self._settings.aws_session_token
        return boto3.client("lexv2-runtime", **kwargs)

    def _base_kwargs(self, session_id: str) -> dict[str, str]:
        return {
            "botId": self._settings.lex_bot_id or "",
            "botAliasId": self._settings.lex_bot_alias_id,
            "localeId": self._settings.lex_locale_id,
            "sessionId": session_id,
        }

    @staticmethod
    def _map_error(exc: Exception, what: str) -> ProviderError:
        code = "unknown"
        try:
            from botocore.exceptions import ClientError  # noqa: PLC0415

            if isinstance(exc, ClientError):
                code = exc.response.get("Error", {}).get("Code", "ClientError")
        except ImportError:  # pragma: no cover
            pass
        friendly = {
            "AccessDeniedException": "Access denied for Lex. The IAM policy is too restrictive.",
            "ResourceNotFoundException": "The Lex bot or alias was not found in this region.",
            "ValidationException": "Lex rejected the request (check the bot, alias and locale).",
            "ThrottlingException": "Lex throttled the request. Try again shortly.",
            "BadRequestException": "Lex rejected the request as malformed.",
        }.get(code, f"AWS Lex returned an error while trying to {what}.")
        return ProviderError(friendly, details={"provider": "aws-lex", "aws_code": code})

    # -- recognition -------------------------------------------------------

    def recognize_text(self, text: str, *, session_id: str) -> LexIntentResult:
        client = self._client()
        started = time.perf_counter()
        try:
            response = client.recognize_text(text=text, **self._base_kwargs(session_id))
        except Exception as exc:
            raise self._map_error(exc, "recognize text") from exc
        return self._parse(
            response,
            transcript=response.get("inputTranscript") or text,
            session_id=session_id,
            started=started,
        )

    def recognize_utterance(
        self,
        audio: bytes,
        *,
        session_id: str,
        content_type: str,
        language: str | None = None,
    ) -> LexIntentResult:
        client = self._client()
        started = time.perf_counter()
        safe_type = _sanitize_content_type(content_type)
        payload = _strip_wav_header(audio, safe_type)
        try:
            response = client.recognize_utterance(
                requestContentType=safe_type,
                responseContentType="audio/mpeg",
                inputStream=payload,
                **self._base_kwargs(session_id),
            )
        except Exception as exc:
            raise self._map_error(exc, "recognize utterance") from exc
        transcript = response.get("inputTranscript") or ""
        return self._parse(
            response,
            transcript=transcript,
            session_id=session_id,
            started=started,
        )

    def _parse(
        self,
        response: dict[str, Any],
        *,
        transcript: str,
        session_id: str,
        started: float,
    ) -> LexIntentResult:
        session_state = response.get("sessionState") or {}
        intent_obj = session_state.get("intent") or {}
        if not intent_obj:
            interpretations = response.get("interpretations") or []
            if interpretations:
                intent_obj = interpretations[0].get("intent") or {}

        intent, warnings = normalize_intent(intent_obj.get("name"))

        raw_slots: dict[str, Any] = {}
        for name, slot in (intent_obj.get("slots") or {}).items():
            if not slot:
                continue
            value = slot.get("value") or {}
            resolved = value.get("interpretedValue") or value.get("originalValue")
            if resolved:
                raw_slots[name] = resolved
        slots, slot_warnings = sanitize_slots(raw_slots)
        warnings.extend(slot_warnings)

        messages = response.get("messages") or []
        fulfillment = " ".join(
            str(message.get("content", "")).strip()
            for message in messages
            if message.get("content")
        ).strip()

        return LexIntentResult(
            transcript=transcript,
            intent=intent,
            slots=slots,
            fulfillment_message=fulfillment,
            provider=self.id,
            simulated=False,
            session_id=session_id,
            latency_ms=int((time.perf_counter() - started) * 1000),
            warnings=warnings,
        )


def _sanitize_content_type(value: str | None) -> str:
    if not value:
        return _DEFAULT_CONTENT_TYPE
    lowered = value.strip().lower()
    if any(lowered.startswith(prefix) for prefix in _ALLOWED_CONTENT_TYPES):
        return value.strip()
    return _DEFAULT_CONTENT_TYPE


def _strip_wav_header(audio: bytes, content_type: str) -> bytes:
    """Strip a 44-byte RIFF/WAVE header if present.

    Lex expects raw PCM. The browser recorder produces a WAV container, so we
    drop the header when we can recognise it.
    """
    if "wav" in content_type and audio[:4] == b"RIFF" and audio[8:12] == b"WAVE":
        return audio[44:]
    return audio
