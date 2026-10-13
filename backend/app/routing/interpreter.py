"""Interpret a user message into a routing decision.

Two strategies are supported:

* **LLM strategy** — when a structured-capable LLM is configured, it receives
  the tool catalogue and must return a JSON decision. Its output is *advisory*;
  the executor still validates everything independently.
* **Heuristic strategy** — a deterministic keyword matcher used in demo mode so
  the application is fully functional without any API key.
"""

from __future__ import annotations

import json
import re
from typing import Any

from ..llm.base import LLMProvider
from ..schemas import Mode, OperationClass
from ..tools.registry import ToolRegistry
from .base import Decision

_INSTANCE_ID_RE = re.compile(r"\bi-[0-9a-f]{8,17}\b", re.IGNORECASE)
_REGION_RE = re.compile(r"\b(?:us|eu|ap|sa|ca|me|af)-[a-z]+-\d\b", re.IGNORECASE)
_TAIL_RE = re.compile(r"\b(\d{1,3})\s*(?:lines|log lines)\b", re.IGNORECASE)

_EXPLANATION_MARKERS = (
    "explain",
    "difference",
    "what is",
    "what's",
    "how do i",
    "how can i",
    "why did",
    "why does",
    "help me understand",
    "tell me about",
    "compare",
)


async def decide(
    *,
    message: str,
    history: list[dict[str, str]],
    mode: Mode,
    registry: ToolRegistry,
    llm: LLMProvider,
    fill_answer: bool = True,
) -> Decision:
    if llm.supports_structured:
        decision = await _llm_decide(
            message=message, history=history, mode=mode, registry=registry, llm=llm
        )
    else:
        decision = _heuristic_decide(message=message, mode=mode, registry=registry)

    if (
        fill_answer
        and decision.operation
        in (OperationClass.conversation, OperationClass.explanation)
        and not decision.reply
    ):
        messages = answer_messages(message, history, mode)
        result = await llm.complete(messages)
        decision.reply = result.text
        decision.provider_used = result.provider
    return decision


# --- LLM strategy ---------------------------------------------------------


def _tool_catalogue(registry: ToolRegistry) -> list[dict[str, Any]]:
    catalogue = []
    for tool in registry.preferred():
        catalogue.append(
            {
                "name": tool.name,
                "description": tool.description,
                "provider": tool.provider,
                "read_only": tool.read_only,
                "available": tool.available,
                "unavailable_reason": tool.unavailable_reason(),
                "parameters": tool.parameters,
            }
        )
    return catalogue


_SYSTEM_PROMPT = (
    "You are Synthia, an assistant for cloud operations. "
    "Decide how to handle the user's request and reply with a single JSON "
    "object and nothing else. Do not wrap it in markdown.\n\n"
    "JSON shape:\n"
    '{"operation": "conversation|explanation|read_only|mutating", '
    '"tool": "<tool name or null>", "arguments": {}, "answer": "<text or null>"}\n\n'
    "Rules:\n"
    "- Use operation 'conversation' for general questions (coding, Linux, general).\n"
    "- Use 'explanation' for cloud concepts, guidance, comparisons, or 'why' "
    "questions. Put the explanation in 'answer'.\n"
    "- Use 'read_only' to call a read-only tool, with the exact tool name and "
    "arguments. Put a short introduction in 'answer' if useful.\n"
    "- Use 'mutating' only for tools marked read_only=false.\n"
    "- Only use tool names from the catalogue. Never invent tools or arguments.\n"
    "- Never claim an action succeeded; the backend executes tools, not you.\n"
)


async def _llm_decide(
    *,
    message: str,
    history: list[dict[str, str]],
    mode: Mode,
    registry: ToolRegistry,
    llm: LLMProvider,
) -> Decision:
    catalogue = _tool_catalogue(registry)
    user = (
        f"Conversation mode: {mode.value}\n"
        f"Available tools (JSON):\n{json.dumps(catalogue)}\n\n"
        f"User request: {message}"
    )
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        *history[-8:],
        {"role": "user", "content": user},
    ]
    result = await llm.complete(messages, temperature=0.0)
    decision = _parse_llm_decision(result.text)
    if decision is None:
        fallback = _heuristic_decide(message=message, mode=mode, registry=registry)
        fallback.warnings.append(
            "The language model returned an unparseable decision; "
            "used deterministic routing instead."
        )
        fallback.provider_used = f"{result.provider} (fallback)"
        return fallback
    decision.provider_used = result.provider
    return decision


def _parse_llm_decision(text: str) -> Decision | None:
    payload = _extract_json(text)
    if payload is None:
        return None
    raw_op = str(payload.get("operation", "conversation")).lower()
    op_map = {
        "conversation": OperationClass.conversation,
        "explanation": OperationClass.explanation,
        "read_only": OperationClass.read_only,
        "readonly": OperationClass.read_only,
        "read-only": OperationClass.read_only,
        "mutating": OperationClass.mutating,
        "tool": OperationClass.read_only,
    }
    operation = op_map.get(raw_op, OperationClass.conversation)
    tool = payload.get("tool") or None
    arguments = payload.get("arguments") or {}
    if not isinstance(arguments, dict):
        arguments = {}
    answer = payload.get("answer")
    if answer is not None and not isinstance(answer, str):
        answer = str(answer)
    return Decision(
        operation=operation if tool or operation in (
            OperationClass.conversation,
            OperationClass.explanation,
        ) else OperationClass.conversation,
        reply=answer,
        tool_name=str(tool) if tool else None,
        arguments=arguments,
    )


def _extract_json(text: str) -> dict[str, Any] | None:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                parsed = json.loads(text[start : end + 1])
                return parsed if isinstance(parsed, dict) else None
            except json.JSONDecodeError:
                return None
    return None


# --- Heuristic strategy ---------------------------------------------------


def _heuristic_decide(
    *, message: str, mode: Mode, registry: ToolRegistry
) -> Decision:
    lowered = message.lower()
    # Tool execution is only inferred in cloud mode so general conversation is
    # never accidentally turned into an infrastructure operation.
    capability = _detect_capability(lowered) if mode == Mode.cloud else None

    # Conceptual questions about resources ("explain the difference between an
    # EC2 instance and a container") must be answered, not executed.
    if _looks_like_explanation(lowered):
        return Decision(
            operation=OperationClass.explanation, provider_used="heuristic"
        )

    if capability:
        tool = _preferred_for_capability(registry, capability)
        if tool is not None:
            arguments = _extract_arguments(lowered)
            return Decision(
                operation=(
                    OperationClass.read_only if tool.read_only else OperationClass.mutating
                ),
                tool_name=tool.name,
                arguments=arguments,
                provider_used="heuristic",
                warnings=(
                    [f"Tool {tool.name} is currently unavailable."]
                    if not tool.available
                    else []
                ),
            )

    if mode == Mode.cloud or any(marker in lowered for marker in _EXPLANATION_MARKERS):
        return Decision(
            operation=OperationClass.explanation,
            provider_used="heuristic",
        )
    return Decision(operation=OperationClass.conversation, provider_used="heuristic")


_EXPLANATION_STARTS = (
    "explain",
    "why ",
    "what ",
    "what's",
    "how ",
    "compare",
    "difference",
    "tell me",
    "help me understand",
    "which is better",
)


def _looks_like_explanation(lowered: str) -> bool:
    text = lowered.lstrip()
    return any(text.startswith(marker) for marker in _EXPLANATION_STARTS)


def _detect_capability(lowered: str) -> str | None:
    wants_logs = any(word in lowered for word in ("log", "logs"))
    wants_detail = any(
        word in lowered for word in ("describe", "detail", "details", "info", "inspect")
    )
    mentions_instance = "ec2" in lowered or "instance" in lowered
    mentions_container = "container" in lowered or "docker" in lowered
    mentions_bucket = "s3" in lowered or "bucket" in lowered

    if mentions_container and wants_logs:
        return "container_logs"
    if mentions_container and wants_detail:
        return "inspect_container"
    if mentions_container:
        return "list_containers"
    if mentions_instance and wants_detail:
        return "describe_instance"
    if mentions_instance:
        return "list_ec2_instances"
    if mentions_bucket:
        return "list_s3_buckets"
    return None


def _preferred_for_capability(registry: ToolRegistry, capability: str):
    for tool in registry.preferred():
        if tool.capability == capability:
            return tool
    return None


def _extract_arguments(lowered: str) -> dict[str, Any]:
    arguments: dict[str, Any] = {}
    instance = _INSTANCE_ID_RE.search(lowered)
    if instance:
        arguments["instance_id"] = instance.group(0)
    region = _REGION_RE.search(lowered)
    if region:
        arguments["region"] = region.group(0)
    tail = _TAIL_RE.search(lowered)
    if tail:
        arguments["tail"] = int(tail.group(1))
    return arguments


def answer_messages(
    message: str, history: list[dict[str, str]], mode: Mode
) -> list[dict[str, str]]:
    system = {
        "role": "system",
        "content": (
            f"You are Synthia, a helpful assistant. Conversation mode: {mode.value}. "
            "Answer clearly and concisely. Never claim to have performed a cloud "
            "action; you can only explain or answer questions."
        ),
    }
    return [system, *history[-10:], {"role": "user", "content": message}]
