"""Pydantic request/response models shared by the API."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, SecretStr, field_validator


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Mode(str, Enum):
    general = "general"
    cloud = "cloud"


class OperationClass(str, Enum):
    """How an interpreted request should be handled."""

    conversation = "conversation"
    explanation = "explanation"
    read_only = "read_only"
    mutating = "mutating"


class TranscriptionStatus(str, Enum):
    """Distinct, debuggable transcription/execution statuses.

    These are deliberately *not* collapsed into a single failure state.
    """

    success = "success"
    empty_transcript = "empty_transcript"
    permission_denied = "permission_denied"
    unsupported_browser = "unsupported_browser"
    network_failure = "network_failure"
    provider_error = "provider_error"
    timeout = "timeout"
    parse_failed = "parse_failed"
    tool_failed = "tool_failed"
    tool_succeeded = "tool_succeeded"


class InputSource(str, Enum):
    speech = "speech"
    typed = "typed"


# --- Chat -----------------------------------------------------------------


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str = Field(min_length=1, max_length=20000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    mode: Mode = Mode.general
    history: list[ChatMessage] = Field(default_factory=list, max_length=50)
    confirmed: bool = False
    session_id: str | None = Field(default=None, max_length=128)

    @field_validator("message")
    @classmethod
    def _strip(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("message must not be blank")
        return stripped


class ToolCall(BaseModel):
    name: str
    provider: str
    read_only: bool
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    requires_confirmation: bool = False
    simulated: bool = False


class ChatResponse(BaseModel):
    id: str
    timestamp: str = Field(default_factory=_now_iso)
    mode: Mode
    operation: OperationClass
    reply: str
    transcript: str
    provider_used: str
    tool_call: ToolCall | None = None
    usage: dict[str, Any] | None = None
    warnings: list[str] = Field(default_factory=list)


# --- Tools ----------------------------------------------------------------


class ToolInfo(BaseModel):
    name: str
    description: str
    provider: str
    read_only: bool
    required_permissions: list[str]
    parameters: dict[str, Any]
    available: bool
    unavailable_reason: str | None = None


class ToolListResponse(BaseModel):
    tools: list[ToolInfo]
    count: int


# --- Providers ------------------------------------------------------------


class ProviderStatus(str, Enum):
    connected = "connected"
    unconfigured = "unconfigured"
    error = "error"
    demo = "demo"
    disabled = "disabled"


class ProviderInfo(BaseModel):
    id: str
    label: str
    status: ProviderStatus
    read_only: bool
    detail: str
    capabilities: list[str] = Field(default_factory=list)
    setup_hint: str | None = None


class ProviderListResponse(BaseModel):
    mode: str
    providers: list[ProviderInfo]


# --- Lex command mode (optional, replaceable) -----------------------------


class LexCommandMode(str, Enum):
    """Where a command result came from. Never conflate the two."""

    live = "live"  # a real AWS Lex V2 response
    simulated = "simulated"  # a clearly labelled local mock response
    disabled = "disabled"  # no provider available


class LexCommandRequest(BaseModel):
    text: str = Field(min_length=1, max_length=8000)
    session_id: str | None = Field(default=None, max_length=128)
    confirmed: bool = False

    @field_validator("text")
    @classmethod
    def _strip(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("text must not be blank")
        return stripped


class LexCommandResponse(BaseModel):
    id: str
    timestamp: str = Field(default_factory=_now_iso)
    transcript: str
    intent: str
    slots: dict[str, str] = Field(default_factory=dict)
    fulfillment_message: str
    mode: LexCommandMode
    provider: str
    session_id: str
    latency_ms: int
    warnings: list[str] = Field(default_factory=list)


class LexStatusResponse(BaseModel):
    enabled: bool
    configured: bool
    available: bool
    mode: LexCommandMode
    provider: str
    detail: str
    setup_hint: str | None = None


# --- Transcriptions (server-side, optional) -------------------------------


class TranscriptionEventCreate(BaseModel):
    transcript: str = Field(default="", max_length=8000)
    provider: str = Field(default="browser-webspeech", max_length=64)
    language: str | None = Field(default=None, max_length=32)
    source: InputSource = InputSource.speech
    status: TranscriptionStatus
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    parsed_intent: str | None = Field(default=None, max_length=128)
    tool_name: str | None = Field(default=None, max_length=128)
    tool_status: TranscriptionStatus | None = None
    error: dict[str, Any] | None = None
    duration_ms: int | None = Field(default=None, ge=0)


class TranscriptionEvent(TranscriptionEventCreate):
    event_id: str
    timestamp: str = Field(default_factory=_now_iso)
    local_only: bool = False


class TranscriptionEventList(BaseModel):
    events: list[TranscriptionEvent]
    count: int
    persistence: str
    note: str


# --- System ---------------------------------------------------------------


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str
    timestamp: str = Field(default_factory=_now_iso)


class DependencyStatus(BaseModel):
    name: str
    ready: bool
    detail: str


class ReadyResponse(BaseModel):
    ready: bool
    service: str
    version: str
    environment: str
    demo_mode: bool
    dependencies: list[DependencyStatus]
    timestamp: str = Field(default_factory=_now_iso)
