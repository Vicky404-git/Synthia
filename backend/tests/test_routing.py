"""Unit tests for the validated tool router / executor."""

from __future__ import annotations

import pytest

from app.config import Settings
from app.errors import (
    ConfirmationRequiredError,
    InvalidToolArgumentsError,
    PermissionDeniedError,
    ProviderNotConfiguredError,
    UnknownToolError,
)
from app.providers.registry import ProviderRegistry
from app.routing.base import Decision
from app.routing.executor import execute_decision
from app.schemas import OperationClass
from app.tools.registry import build_tool_registry


def _registry(**overrides):
    settings = Settings(rate_limit_per_minute=0, **overrides)
    providers = ProviderRegistry(settings)
    return settings, build_tool_registry(settings, providers)


async def test_unknown_tool_is_rejected():
    settings, registry = _registry(demo_mode=True)
    decision = Decision(operation=OperationClass.read_only, tool_name="evil.shell")
    with pytest.raises(UnknownToolError):
        await execute_decision(decision, settings=settings, registry=registry)


async def test_invalid_arguments_are_rejected():
    settings, registry = _registry(demo_mode=True)
    decision = Decision(
        operation=OperationClass.read_only,
        tool_name="demo.list_ec2_instances",
        arguments={"bogus": "nope"},
    )
    with pytest.raises(InvalidToolArgumentsError):
        await execute_decision(decision, settings=settings, registry=registry)


async def test_unconfigured_provider_is_reported():
    settings, registry = _registry(demo_mode=False, aws_enabled=False)
    decision = Decision(
        operation=OperationClass.read_only, tool_name="aws.list_ec2_instances"
    )
    with pytest.raises(ProviderNotConfiguredError):
        await execute_decision(decision, settings=settings, registry=registry)


async def test_mutating_denied_without_opt_in():
    settings, registry = _registry(demo_mode=True, allow_mutating=False)
    decision = Decision(
        operation=OperationClass.mutating,
        tool_name="demo.simulated_action",
        arguments={"action": "restart", "target": "synthia-api"},
    )
    with pytest.raises(PermissionDeniedError):
        await execute_decision(decision, settings=settings, registry=registry)


async def test_mutating_requires_confirmation():
    settings, registry = _registry(demo_mode=True, allow_mutating=True)
    decision = Decision(
        operation=OperationClass.mutating,
        tool_name="demo.simulated_action",
        arguments={"action": "restart", "target": "synthia-api"},
    )
    with pytest.raises(ConfirmationRequiredError):
        await execute_decision(
            decision, settings=settings, registry=registry, confirmed=False
        )


async def test_mutating_succeeds_with_confirmation_and_is_simulated():
    settings, registry = _registry(demo_mode=True, allow_mutating=True)
    decision = Decision(
        operation=OperationClass.mutating,
        tool_name="demo.simulated_action",
        arguments={"action": "restart", "target": "synthia-api"},
    )
    outcome = await execute_decision(
        decision, settings=settings, registry=registry, confirmed=True
    )
    assert outcome.tool_call is not None
    assert outcome.tool_call.simulated is True
    assert outcome.tool_call.result["performed"] is False


async def test_provider_error_propagates():
    from app.errors import ProviderError

    settings, registry = _registry(demo_mode=True)
    tool = registry.get("demo.list_ec2_instances")
    original = tool.handler

    def boom(_args):
        raise ProviderError("upstream exploded", details={"provider": "demo"})

    tool.handler = boom
    try:
        decision = Decision(
            operation=OperationClass.read_only, tool_name="demo.list_ec2_instances"
        )
        with pytest.raises(ProviderError):
            await execute_decision(decision, settings=settings, registry=registry)
    finally:
        tool.handler = original


def test_registry_preferred_prefers_real_provider_when_available():
    settings, registry = _registry(demo_mode=True)
    # AWS unavailable -> demo tool is preferred for the EC2 capability.
    ec2 = next(t for t in registry.preferred() if t.capability == "list_ec2_instances")
    assert ec2.name == "demo.list_ec2_instances"
