"""Assistant chat and validated tool-routing endpoints."""

from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from ..auth import client_key, ensure_authorized, get_rate_limiter
from ..config import get_settings
from ..errors import SynthiaError, ValidationError
from ..llm import get_llm_provider
from ..routing import decide, execute_decision
from ..routing.interpreter import answer_messages
from ..schemas import ChatRequest, ChatResponse, OperationClass
from ..tools import get_tool_registry

router = APIRouter(prefix="/api", tags=["chat"])

_TOOL_OPERATIONS = (OperationClass.read_only, OperationClass.mutating)


def _validate_length(message: str) -> None:
    settings = get_settings()
    if len(message) > settings.max_request_chars:
        raise ValidationError(
            "Message exceeds the configured maximum length.",
            details={"max_request_chars": settings.max_request_chars},
        )


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, request: Request) -> ChatResponse:
    settings = get_settings()
    get_rate_limiter().check(client_key(request))
    _validate_length(req.message)

    registry = get_tool_registry()
    llm = get_llm_provider()
    history = [message.model_dump() for message in req.history]

    decision = await decide(
        message=req.message,
        history=history,
        mode=req.mode,
        registry=registry,
        llm=llm,
    )
    if decision.operation in _TOOL_OPERATIONS:
        ensure_authorized(request.headers.get("authorization"))

    outcome = await execute_decision(
        decision,
        settings=settings,
        registry=registry,
        history=req.history,
        confirmed=req.confirmed,
    )

    return ChatResponse(
        id=uuid.uuid4().hex,
        mode=req.mode,
        operation=outcome.operation,
        reply=outcome.reply,
        transcript=req.message,
        provider_used=decision.provider_used,
        tool_call=outcome.tool_call,
        warnings=outcome.warnings,
    )


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


@router.post("/chat/stream")
async def chat_stream(req: ChatRequest, request: Request) -> StreamingResponse:
    settings = get_settings()
    get_rate_limiter().check(client_key(request))
    _validate_length(req.message)
    registry = get_tool_registry()
    llm = get_llm_provider()
    history = [message.model_dump() for message in req.history]

    async def event_stream():
        try:
            decision = await decide(
                message=req.message,
                history=history,
                mode=req.mode,
                registry=registry,
                llm=llm,
                fill_answer=False,
            )
            if decision.operation in _TOOL_OPERATIONS:
                ensure_authorized(request.headers.get("authorization"))
                outcome = await execute_decision(
                    decision,
                    settings=settings,
                    registry=registry,
                    history=req.history,
                    confirmed=req.confirmed,
                )
                response = ChatResponse(
                    id=uuid.uuid4().hex,
                    mode=req.mode,
                    operation=outcome.operation,
                    reply=outcome.reply,
                    transcript=req.message,
                    provider_used=decision.provider_used,
                    tool_call=outcome.tool_call,
                    warnings=outcome.warnings,
                )
                yield _sse(
                    {
                        "type": "result",
                        "response": response.model_dump(mode="json"),
                    }
                )
                yield _sse({"type": "done"})
                return

            messages = answer_messages(req.message, history, req.mode)
            collected: list[str] = []
            async for token in llm.stream(messages):
                collected.append(token)
                yield _sse({"type": "token", "value": token})
            yield _sse(
                {
                    "type": "done",
                    "response": {
                        "id": uuid.uuid4().hex,
                        "mode": req.mode.value,
                        "operation": decision.operation.value,
                        "reply": "".join(collected),
                        "transcript": req.message,
                        "provider_used": llm.id,
                        "tool_call": None,
                        "warnings": decision.warnings,
                    },
                }
            )
        except SynthiaError as exc:
            yield _sse({"type": "error", "error": exc.to_payload()["error"]})
        except Exception:  # noqa: BLE001 - never leak internals in a stream
            yield _sse(
                {
                    "type": "error",
                    "error": {
                        "code": "internal_error",
                        "message": "An unexpected error occurred while streaming.",
                        "details": {},
                    },
                }
            )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
