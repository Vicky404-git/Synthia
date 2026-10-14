"""Voice-command tests using mocks (no real AWS calls, no credentials).

Covers the AWS Lex request construction, response parsing, error mapping,
missing configuration, the simulated provider, allowlist validation, and the
FastAPI routes including provider fallback.
"""

from __future__ import annotations

from botocore.exceptions import ClientError

from app.config import Settings
from app.errors import ProviderError, ProviderNotConfiguredError
from app.lex import (
    AWSLexProvider,
    MockLexProvider,
    get_lex_provider,
    resolve_session_id,
)
from app.lex import policy


class _FakeLexClient:
    """Records calls and returns a canned response or raises a canned error."""

    def __init__(self, response: dict | None = None, error: Exception | None = None):
        self.response = response or {}
        self.error = error
        self.calls: list[tuple[str, dict]] = []

    def recognize_text(self, **kwargs):
        self.calls.append(("recognize_text", kwargs))
        if self.error:
            raise self.error
        return self.response

    def recognize_utterance(self, **kwargs):
        self.calls.append(("recognize_utterance", kwargs))
        if self.error:
            raise self.error
        return self.response


def _aws_provider(settings: Settings | None = None) -> AWSLexProvider:
    settings = settings or Settings(
        lex_enabled=True, lex_bot_id="bot123", lex_bot_alias_id="ALIAS1"
    )
    return AWSLexProvider(settings)


# --- request construction --------------------------------------------------


def test_recognize_text_builds_expected_request():
    client = _FakeLexClient(response={"messages": []})
    provider = _aws_provider()
    provider._client = lambda: client  # type: ignore[assignment]

    provider.recognize_text("turn on the fan", session_id="sess-42")

    name, kwargs = client.calls[0]
    assert name == "recognize_text"
    assert kwargs["botId"] == "bot123"
    assert kwargs["botAliasId"] == "ALIAS1"
    assert kwargs["localeId"] == "en_US"
    assert kwargs["sessionId"] == "sess-42"
    assert kwargs["text"] == "turn on the fan"


def test_recognize_utterance_forwards_audio_and_content_type():
    client = _FakeLexClient(
        response={"inputTranscript": "turn off the light", "messages": []}
    )
    provider = _aws_provider()
    provider._client = lambda: client  # type: ignore[assignment]

    wav = b"RIFF" + b"\x00" * 4 + b"WAVE" + b"\x00" * 32 + b"payload-audio"
    result = provider.recognize_utterance(
        wav,
        session_id="sess-9",
        content_type="audio/wav",
    )

    _, kwargs = client.calls[0]
    assert kwargs["inputStream"] == b"payload-audio"  # 44-byte header stripped
    assert kwargs["requestContentType"] == "audio/wav"
    assert result.transcript == "turn off the light"
    assert result.simulated is False


def test_utterance_rejects_arbitrary_content_type():
    client = _FakeLexClient(response={"messages": []})
    provider = _aws_provider()
    provider._client = lambda: client  # type: ignore[assignment]

    provider.recognize_utterance(
        b"raw", session_id="s", content_type="text/html; <script>"
    )
    _, kwargs = client.calls[0]
    assert kwargs["requestContentType"] == "audio/l16; rate=16000; channels=1"


# --- response parsing ------------------------------------------------------


def test_parse_extracts_intent_slots_and_message():
    response = {
        "inputTranscript": "turn on the bedroom fan",
        "sessionState": {
            "intent": {
                "name": "DeviceControlIntent",
                "slots": {
                    "Action": {"value": {"interpretedValue": "turn_on"}},
                    "Device": {"value": {"originalValue": "fan"}},
                    "Room": {"value": {"interpretedValue": "bedroom"}},
                    "Secret": {"value": {"interpretedValue": "should-drop"}},
                },
            }
        },
        "messages": [{"content": "Okay, turning it on.", "contentType": "PlainText"}],
    }
    provider = _aws_provider()
    provider._client = lambda: _FakeLexClient(response=response)  # type: ignore[assignment]

    result = provider.recognize_text("turn on the bedroom fan", session_id="s")

    assert result.intent == "DeviceControlIntent"
    assert result.slots == {"Action": "turn_on", "Device": "fan", "Room": "bedroom"}
    assert result.fulfillment_message == "Okay, turning it on."
    assert result.simulated is False
    assert any("Secret" in warning for warning in result.warnings)


def test_parse_falls_back_when_intent_unknown():
    response = {
        "sessionState": {"intent": {"name": "SomethingElse", "slots": {}}},
        "messages": [],
    }
    provider = _aws_provider()
    provider._client = lambda: _FakeLexClient(response=response)  # type: ignore[assignment]

    result = provider.recognize_text("blah", session_id="s")

    assert result.intent == "FallbackIntent"
    assert result.warnings


def test_parse_uses_interpretations_when_session_state_missing():
    response = {
        "interpretations": [
            {"intent": {"name": "QueryStatusIntent", "slots": {}}}
        ],
        "messages": [{"content": "It is on.", "contentType": "PlainText"}],
    }
    provider = _aws_provider()
    provider._client = lambda: _FakeLexClient(response=response)  # type: ignore[assignment]

    result = provider.recognize_text("status?", session_id="s")
    assert result.intent == "QueryStatusIntent"


# --- errors and configuration ---------------------------------------------


def test_aws_error_is_mapped_without_leaking_details():
    error = ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": "secret-detail"}},
        "RecognizeText",
    )
    provider = _aws_provider()
    provider._client = lambda: _FakeLexClient(error=error)  # type: ignore[assignment]

    try:
        provider.recognize_text("hi", session_id="s")
    except ProviderError as exc:
        assert exc.details["aws_code"] == "AccessDeniedException"
        assert "secret-detail" not in exc.message
    else:  # pragma: no cover
        raise AssertionError("expected ProviderError")


def test_missing_bot_configuration_is_reported():
    provider = AWSLexProvider(Settings(lex_enabled=True, lex_bot_id=None))
    health = provider.health()
    assert health.status.value == "unconfigured"
    try:
        provider.recognize_text("hi", session_id="s")
    except ProviderNotConfiguredError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected ProviderNotConfiguredError")


def test_disabled_health_reports_disabled():
    health = AWSLexProvider(Settings(lex_enabled=False)).health()
    assert health.status.value == "disabled"
    assert health.simulated is False


def test_factory_uses_mock_when_disabled():
    provider = get_lex_provider()
    assert isinstance(provider, MockLexProvider)


def test_factory_uses_aws_when_configured(monkeypatch):
    monkeypatch.setenv("LEX_ENABLED", "true")
    monkeypatch.setenv("LEX_BOT_ID", "bot123")
    from app.config import get_settings
    from app.lex import reset_lex_provider

    get_settings.cache_clear()
    reset_lex_provider()
    try:
        assert isinstance(get_lex_provider(), AWSLexProvider)
    finally:
        get_settings.cache_clear()
        reset_lex_provider()


# --- session ids -----------------------------------------------------------


def test_session_ids_are_not_shared():
    first = resolve_session_id(None, "synthia")
    second = resolve_session_id(None, "synthia")
    assert first != second
    assert first.startswith("synthia-")


def test_session_id_is_sanitized():
    assert resolve_session_id("user 1<script>", "synthia") == "user-1-script-"


# --- allowlist policy ------------------------------------------------------


def test_policy_drops_unknown_slots_and_normalizes_intent():
    intent, warnings = policy.normalize_intent("HackIntent")
    assert intent == "FallbackIntent"
    assert warnings
    slots, slot_warnings = policy.sanitize_slots(
        {"Action": "turn_on", "Evil": "x"}
    )
    assert slots == {"Action": "turn_on"}
    assert slot_warnings


# --- simulated provider ----------------------------------------------------


def test_mock_provider_control_and_query():
    provider = MockLexProvider(Settings())
    result = provider.recognize_text("turn on the kitchen light", session_id="s")
    assert result.intent == "DeviceControlIntent"
    assert result.simulated is True
    assert result.slots["Device"] == "light"
    assert "DEMO" in result.fulfillment_message

    query = provider.recognize_text("what is the state of the kitchen light", session_id="s")
    assert query.intent == "QueryStatusIntent"
    assert "on" in query.fulfillment_message


def test_mock_provider_fallback():
    result = MockLexProvider(Settings()).recognize_text("banana", session_id="s")
    assert result.intent == "FallbackIntent"


# --- FastAPI routes --------------------------------------------------------


def test_status_route_defaults_to_simulated(client):
    body = client.get("/api/lex/status").json()
    assert body["mode"] == "simulated"
    assert body["provider"] == "mock-lex"
    assert body["available"] is True


def test_command_route_returns_structured_result(client):
    response = client.post(
        "/api/lex/command",
        json={"text": "set the AC to 22", "session_id": "sess-a"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "DeviceControlIntent"
    assert body["slots"]["Value"] == "22"
    assert body["mode"] == "simulated"
    assert body["session_id"] == "sess-a"


def test_command_route_rejects_blank_text(client):
    response = client.post("/api/lex/command", json={"text": "   "})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_ready_includes_lex_dependency(client):
    body = client.get("/ready").json()
    names = {dep["name"] for dep in body["dependencies"]}
    assert "lex" in names


def test_voice_route_with_transcript(client):
    response = client.post(
        "/api/lex/voice",
        data={"transcript": "turn off the bedroom fan", "session_id": "sess-v"},
        files={"file": ("clip.wav", b"RIFFxxxxWAVE", "audio/wav")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "DeviceControlIntent"
    assert body["mode"] == "simulated"
