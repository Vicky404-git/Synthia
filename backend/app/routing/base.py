"""Routing decision types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..schemas import OperationClass


@dataclass
class Decision:
    operation: OperationClass
    reply: str | None = None
    tool_name: str | None = None
    arguments: dict[str, Any] = field(default_factory=dict)
    provider_used: str = "heuristic"
    warnings: list[str] = field(default_factory=list)
