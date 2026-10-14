"""Base types for the optional, replaceable voice-command intent provider.

The rest of the application depends only on this small contract, never on AWS
Lex directly. A finished AWS Lex V2 integration, a local rule-based
recogniser, or a future custom model can each implement :class:`LexProvider`
without touching the API layer.

This mirrors the existing ``STTProvider`` / ``LLMProvider`` seams so the
recognition stack is swappable end to end.
"""

from __future__ import annotations

import re
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from ..schemas import ProviderStatus

# Session ids are supplied by the browser (one per logical conversation). We
# keep them short, safe, and unique per caller rather than reusing any global
# hardcoded id.
_SESSION_SAFE = re.compile(r"[^a-zA-Z0-9._:-]")
_MAX_SESSION_LEN = 100


@dataclass
class LexHealth:
    status: ProviderStatus
    detail: str
    provider: str
    simulated: bool
    setup_hint: str | None = None


@dataclass
class LexIntentResult:
    """A small, stable view of a recognition result.

    Only the fields the UI needs are kept, so neither the frontend nor the
    tool boundary ever depends on the full AWS response shape.
    """

    transcript: str
    intent: str
    slots: dict[str, str]
    fulfillment_message: str
    provider: str
    simulated: bool
    session_id: str
    latency_ms: int
    warnings: list[str] = field(default_factory=list)


class LexProvider(ABC):
    id: str = "base"

    @property
    @abstractmethod
    def available(self) -> bool: ...

    @abstractmethod
    def health(self) -> LexHealth: ...

    @abstractmethod
    def recognize_text(self, text: str, *, session_id: str) -> LexIntentResult:
        """Recognise intent/slots/messages from a text transcript."""

    def recognize_utterance(
        self,
        audio: bytes,
        *,
        session_id: str,
        content_type: str,
        language: str | None = None,
    ) -> LexIntentResult:
        """Recognise directly from audio.

        Optional: only providers that can genuinely stream audio implement it.
        Callers must treat :class:`NotImplementedError` as "use STT first".
        """
        raise NotImplementedError


def resolve_session_id(provided: str | None, prefix: str) -> str:
    """Return a safe, per-caller session id.

    Uses the caller-supplied id when present, otherwise generates a fresh one.
    This avoids the hardcoded shared-session anti-pattern.
    """
    if provided:
        cleaned = _SESSION_SAFE.sub("-", provided.strip())[:_MAX_SESSION_LEN]
        if cleaned:
            return cleaned
    return f"{_SESSION_SAFE.sub('-', prefix) or 'synthia'}-{uuid.uuid4().hex}"
