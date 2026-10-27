"""Execute a validated routing decision.

Safety rules enforced here (independently of the LLM):

* Unknown tools are rejected.
* Tool arguments are validated against a Pydantic schema (extra keys rejected).
* Unavailable providers produce a clear "not configured" error.
* Mutating tools require ``ALLOW_MUTATING=true`` **and** explicit confirmation.
* Tool handlers are the only code that runs — never arbitrary LLM output.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from starlette.concurrency import run_in_threadpool

from ..config import Settings
from ..errors import (
    ConfirmationRequiredError,
    PermissionDeniedError,
    ProviderNotConfiguredError,
)
from ..schemas import ChatMessage, OperationClass, ToolCall
from ..tools.registry import ToolRegistry
from .base import Decision


@dataclass
class ExecutionOutcome:
    operation: OperationClass
    reply: str
    tool_call: ToolCall | None = None
    warnings: list[str] = field(default_factory=list)


async def execute_decision(
    decision: Decision,
    *,
    settings: Settings,
    registry: ToolRegistry,
    history: list[ChatMessage] | None = None,
    confirmed: bool = False,
) -> ExecutionOutcome:
    warnings = list(decision.warnings)

    if decision.operation in (
        OperationClass.conversation,
        OperationClass.explanation,
    ):
        return ExecutionOutcome(
            operation=decision.operation,
            reply=decision.reply or "",
            warnings=warnings,
        )

    # --- tool path --------------------------------------------------------
    tool, parsed = registry.validate(decision.tool_name or "", decision.arguments)

    if not tool.available:
        raise ProviderNotConfiguredError(
            tool.unavailable_reason() or "This tool is not available.",
            details={"tool": tool.name, "provider": tool.provider},
        )

    _check_permissions(tool.read_only, settings, confirmed)

    # Human-in-the-Loop gate: do not execute cloud/provider tools directly;
    # return a pending approval payload for the UI to confirm.
    arguments = parsed.model_dump(exclude_none=True)
    if decision.operation == OperationClass.mutating or not tool.read_only or tool.provider != "demo":
        return ExecutionOutcome(
            operation=decision.operation,
            reply=(
                "Tool execution requires human approval.\n\n"
                + _format_pending(tool.name, tool.provider, arguments)
            ),
            tool_call=ToolCall(
                name=tool.name,
                provider=tool.provider,
                read_only=tool.read_only,
                arguments=arguments,
                result={"status": "pending_approval", "tool": tool.name, "arguments": arguments},
                requires_confirmation=True,
                simulated=False,
            ),
            warnings=warnings,
        )

    result = await run_in_threadpool(tool.handler, parsed)

    arguments = parsed.model_dump(exclude_none=True)
    tool_call = ToolCall(
        name=tool.name,
        provider=tool.provider,
        read_only=tool.read_only,
        arguments=arguments,
        result=result.data,
        requires_confirmation=False,
        simulated=result.simulated,
    )
    reply = _summarise(tool.name, result.message, result.simulated, result.data)
    if result.simulated:
        warnings.append("Result is simulated demo data, not a live provider response.")
    return ExecutionOutcome(
        operation=decision.operation,
        reply=reply,
        tool_call=tool_call,
        warnings=warnings,
    )


def _check_permissions(read_only: bool, settings: Settings, confirmed: bool) -> None:
    if read_only:
        return
    if not settings.allow_mutating:
        raise PermissionDeniedError(
            "Mutating operations are disabled. V1 defaults to read-only cloud "
            "tools (set ALLOW_MUTATING=true to opt in).",
            details={"permission": "cloud.write"},
        )
    if not confirmed:
        raise ConfirmationRequiredError(
            "This is a mutating operation and requires explicit confirmation.",
            details={"requires_confirmation": True},
        )


def _summarise(
    tool_name: str, message: str, simulated: bool, data: dict[str, Any]
) -> str:
    prefix = "DEMO — " if simulated else ""
    lines = [f"{prefix}{message}".strip()]
    if isinstance(data, dict) and data.get("status") == "pending_approval":
        return "\n".join(lines)
    if "instances" in data and isinstance(data["instances"], list):
        for item in data["instances"][:10]:
            lines.append(
                f"  • {item.get('id')}  {item.get('name','')}  "
                f"{item.get('type','')}  {item.get('state','')}"
            )
    if "buckets" in data and isinstance(data["buckets"], list):
        for item in data["buckets"][:20]:
            lines.append(f"  • {item.get('name')}")
    if "containers" in data and isinstance(data["containers"], list):
        for item in data["containers"][:20]:
            lines.append(
                f"  • {item.get('name')}  {item.get('image','')}  {item.get('state','')}"
            )
    if "lines" in data and isinstance(data["lines"], list):
        lines.append("```")
        lines.extend(str(line) for line in data["lines"])
        lines.append("```")
    lines.append(f"[tool: {tool_name}]")
    return "\n".join(lines)


def _format_pending(tool_name: str, provider: str, arguments: dict[str, Any]) -> str:
    import json

    payload = {"status": "pending_approval", "tool": tool_name, "arguments": arguments}
    return json.dumps(payload)
