"""Base interface for replaceable LLM providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LLMResult:
    text: str
    provider: str
    model: str
    usage: dict[str, Any] | None = field(default=None)


class LLMProvider(ABC):
    """A minimal chat-completion interface.

    ``supports_structured`` indicates whether the provider can reliably return
    machine-parseable JSON decisions. When false, the intent interpreter falls
    back to deterministic heuristics.
    """

    id: str = "base"
    supports_structured: bool = False

    @property
    @abstractmethod
    def model(self) -> str: ...

    @abstractmethod
    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int | None = None,
        temperature: float = 0.2,
    ) -> LLMResult: ...

    @abstractmethod
    def stream(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int | None = None,
        temperature: float = 0.2,
    ) -> AsyncIterator[str]: ...
