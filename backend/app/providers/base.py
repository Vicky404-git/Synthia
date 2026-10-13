"""Base types shared by all cloud provider adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from ..schemas import ProviderStatus


@dataclass
class ProviderHealth:
    status: ProviderStatus
    detail: str
    capabilities: list[str] = field(default_factory=list)
    setup_hint: str | None = None


@dataclass
class ProviderResult:
    """Structured result returned by an adapter operation."""

    data: dict[str, Any]
    provider: str
    simulated: bool = False
    message: str = ""


class CloudProvider(ABC):
    id: str = "base"
    label: str = "Base"
    read_only: bool = True

    @abstractmethod
    def health(self) -> ProviderHealth: ...

    @abstractmethod
    def capabilities(self) -> list[str]: ...

    def execute(self, operation: str, arguments: dict[str, Any]) -> ProviderResult:
        """Optional generic dispatch. Concrete adapters may override."""
        raise NotImplementedError
