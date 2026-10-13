"""Registered tool catalogue and direct, validated tool execution."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from ..auth import client_key, ensure_authorized, get_rate_limiter, require_auth
from ..config import get_settings
from ..routing import execute_decision
from ..routing.base import Decision
from ..schemas import OperationClass, ToolInfo, ToolListResponse
from ..tools import get_tool_registry

router = APIRouter(prefix="/api", tags=["tools"])


class ToolExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    arguments: dict[str, Any] = Field(default_factory=dict)
    confirmed: bool = False


class ToolExecuteResponse(BaseModel):
    name: str
    provider: str
    read_only: bool
    simulated: bool
    requires_confirmation: bool
    arguments: dict[str, Any]
    result: dict[str, Any] | None
    message: str


@router.get("/tools", response_model=ToolListResponse)
async def list_tools() -> ToolListResponse:
    registry = get_tool_registry()
    tools = [
        ToolInfo(
            name=tool.name,
            description=tool.description,
            provider=tool.provider,
            read_only=tool.read_only,
            required_permissions=tool.permissions,
            parameters=tool.parameters,
            available=tool.available,
            unavailable_reason=tool.unavailable_reason(),
        )
        for tool in registry.all()
    ]
    return ToolListResponse(tools=tools, count=len(tools))


@router.post(
    "/tools/execute",
    response_model=ToolExecuteResponse,
    dependencies=[Depends(require_auth)],
)
async def execute_tool(payload: ToolExecuteRequest, request: Request) -> ToolExecuteResponse:
    settings = get_settings()
    get_rate_limiter().check(client_key(request))
    # Direct execution always requires the token when one is configured, even
    # for read-only tools, because it can reach real infrastructure.
    ensure_authorized(request.headers.get("authorization"))

    registry = get_tool_registry()
    tool = registry.require(payload.name)
    decision = Decision(
        operation=(
            OperationClass.read_only if tool.read_only else OperationClass.mutating
        ),
        tool_name=payload.name,
        arguments=payload.arguments,
    )
    outcome = await execute_decision(
        decision,
        settings=settings,
        registry=registry,
        confirmed=payload.confirmed,
    )
    call = outcome.tool_call
    assert call is not None  # tool operations always produce a tool call
    return ToolExecuteResponse(
        name=call.name,
        provider=call.provider,
        read_only=call.read_only,
        simulated=call.simulated,
        requires_confirmation=False,
        arguments=call.arguments,
        result=call.result,
        message=outcome.reply,
    )
