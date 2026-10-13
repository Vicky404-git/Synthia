"""Tool definition and execution result types."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from ..providers.base import ProviderResult


@dataclass
class Tool:
    name: str
    capability: str
    description: str
    provider: str
    read_only: bool
    permissions: list[str]
    args_model: type[BaseModel]
    handler: Callable[[BaseModel], ProviderResult]
    # Returns None when the tool can run, or a human-readable reason otherwise.
    availability: Callable[[], str | None] = field(default=lambda: None)

    @property
    def parameters(self) -> dict[str, Any]:
        schema = self.args_model.model_json_schema()
        schema.pop("title", None)
        return schema

    @property
    def available(self) -> bool:
        return self.availability() is None

    def unavailable_reason(self) -> str | None:
        return self.availability()


@dataclass
class ToolExecution:
    tool: Tool
    result: ProviderResult
    arguments: dict[str, Any]
