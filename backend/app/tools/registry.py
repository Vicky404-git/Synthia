"""Tool registry: named, validated, permission-aware cloud operations."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ..config import Settings, get_settings
from ..errors import InvalidToolArgumentsError, UnknownToolError
from ..providers.registry import ProviderRegistry, get_provider_registry
from ..schemas import ProviderStatus
from .base import Tool


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ListEc2Args(_Base):
    region: str | None = Field(
        default=None, description="AWS region, e.g. us-east-1. Defaults to config."
    )


class DescribeInstanceArgs(_Base):
    instance_id: str = Field(description="The EC2 instance id, e.g. i-0123456789abcdef0.")
    region: str | None = Field(default=None, description="AWS region override.")


class ListS3Args(_Base):
    pass


class ListContainersArgs(_Base):
    all: bool = Field(
        default=False, description="Include stopped containers, not just running ones."
    )


class InspectContainerArgs(_Base):
    container_id: str = Field(description="Container id or name.")


class ContainerLogsArgs(_Base):
    container_id: str = Field(description="Container id or name.")
    tail: int = Field(default=50, ge=1, le=500, description="Number of log lines.")


class SimulatedActionArgs(_Base):
    action: str = Field(default="noop", description="A labelled, simulated action name.")
    target: str = Field(default="demo", description="Simulated target identifier.")


class ToolRegistry:
    def __init__(self, tools: list[Tool]) -> None:
        self._tools: dict[str, Tool] = {tool.name: tool for tool in tools}

    def all(self) -> list[Tool]:
        return list(self._tools.values())

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def require(self, name: str) -> Tool:
        tool = self.get(name)
        if tool is None:
            raise UnknownToolError(
                f"Unknown tool: {name!r}.", details={"tool": name}
            )
        return tool

    def validate(self, name: str, arguments: dict | None) -> tuple[Tool, BaseModel]:
        tool = self.require(name)
        try:
            parsed = tool.args_model.model_validate(arguments or {})
        except Exception as exc:  # pydantic ValidationError
            raise InvalidToolArgumentsError(
                f"Invalid arguments for tool {name!r}.",
                details={"tool": name, "reason": _validation_reason(exc)},
            ) from exc
        return tool, parsed

    def preferred(self) -> list[Tool]:
        """One tool per capability, preferring configured real providers.

        Demo tools are only surfaced when demo mode is on and the real provider
        is not available. When nothing is available, the real provider's tool is
        returned so its unavailability reason can be reported.
        """
        by_capability: dict[str, list[Tool]] = {}
        for tool in self._tools.values():
            by_capability.setdefault(tool.capability, []).append(tool)

        priority = {"aws": 0, "docker": 0, "azure": 1, "demo": 2}
        selected: list[Tool] = []
        for tools in by_capability.values():
            ordered = sorted(tools, key=lambda t: priority.get(t.provider, 5))
            available = [t for t in ordered if t.available]
            if available:
                selected.append(available[0])
            else:
                real = [t for t in ordered if t.provider != "demo"]
                selected.append(real[0] if real else ordered[0])
        return selected


def _validation_reason(exc: Exception) -> str:
    errors = getattr(exc, "errors", None)
    if callable(errors):
        try:
            return "; ".join(
                f"{'.'.join(str(p) for p in err.get('loc', []))}: {err.get('msg')}"
                for err in errors()
            )
        except Exception:  # pragma: no cover - defensive
            return "argument validation failed"
    return "argument validation failed"


def build_tool_registry(
    settings: Settings, providers: ProviderRegistry
) -> ToolRegistry:
    aws = providers.get("aws")
    docker = providers.get("docker")
    demo = providers.get("demo")

    def aws_avail() -> str | None:
        health = aws.health()
        if health.status == ProviderStatus.connected:
            return None
        return health.detail

    def docker_avail() -> str | None:
        health = docker.health()
        if health.status == ProviderStatus.connected:
            return None
        return health.detail

    def demo_avail() -> str | None:
        if settings.demo_mode:
            return None
        return "Demo mode is disabled (DEMO_MODE=false)."

    tools: list[Tool] = [
        # --- AWS (read-only) ---
        Tool(
            name="aws.list_ec2_instances",
            capability="list_ec2_instances",
            description="List EC2 instances in the configured AWS region.",
            provider="aws",
            read_only=True,
            permissions=["cloud.aws.read"],
            args_model=ListEc2Args,
            handler=lambda args: aws.list_ec2_instances(region=args.region),
            availability=aws_avail,
        ),
        Tool(
            name="aws.describe_instance",
            capability="describe_instance",
            description="Describe a single EC2 instance by id.",
            provider="aws",
            read_only=True,
            permissions=["cloud.aws.read"],
            args_model=DescribeInstanceArgs,
            handler=lambda args: aws.describe_instance(
                instance_id=args.instance_id, region=args.region
            ),
            availability=aws_avail,
        ),
        Tool(
            name="aws.list_s3_buckets",
            capability="list_s3_buckets",
            description="List S3 buckets visible to the configured credentials.",
            provider="aws",
            read_only=True,
            permissions=["cloud.aws.read"],
            args_model=ListS3Args,
            handler=lambda args: aws.list_s3_buckets(),
            availability=aws_avail,
        ),
        # --- Docker (read-only) ---
        Tool(
            name="docker.list_containers",
            capability="list_containers",
            description="List local Docker containers.",
            provider="docker",
            read_only=True,
            permissions=["cloud.docker.read"],
            args_model=ListContainersArgs,
            handler=lambda args: docker.list_containers(all=args.all),
            availability=docker_avail,
        ),
        Tool(
            name="docker.inspect_container",
            capability="inspect_container",
            description="Inspect a local Docker container.",
            provider="docker",
            read_only=True,
            permissions=["cloud.docker.read"],
            args_model=InspectContainerArgs,
            handler=lambda args: docker.inspect_container(container_id=args.container_id),
            availability=docker_avail,
        ),
        Tool(
            name="docker.container_logs",
            capability="container_logs",
            description="Read a bounded number of log lines from a container.",
            provider="docker",
            read_only=True,
            permissions=["cloud.docker.read"],
            args_model=ContainerLogsArgs,
            handler=lambda args: docker.container_logs(
                container_id=args.container_id, tail=args.tail
            ),
            availability=docker_avail,
        ),
        # --- Demo (labelled simulated data) ---
        Tool(
            name="demo.list_ec2_instances",
            capability="list_ec2_instances",
            description="List labelled sample EC2 instances (demo data).",
            provider="demo",
            read_only=True,
            permissions=["cloud.demo.read"],
            args_model=ListEc2Args,
            handler=lambda args: demo.list_ec2_instances(region=args.region),
            availability=demo_avail,
        ),
        Tool(
            name="demo.list_s3_buckets",
            capability="list_s3_buckets",
            description="List labelled sample S3 buckets (demo data).",
            provider="demo",
            read_only=True,
            permissions=["cloud.demo.read"],
            args_model=ListS3Args,
            handler=lambda args: demo.list_s3_buckets(),
            availability=demo_avail,
        ),
        Tool(
            name="demo.list_containers",
            capability="list_containers",
            description="List labelled sample containers (demo data).",
            provider="demo",
            read_only=True,
            permissions=["cloud.demo.read"],
            args_model=ListContainersArgs,
            handler=lambda args: demo.list_containers(all=args.all),
            availability=demo_avail,
        ),
        # --- Mutating demo tool (confirmation-gated, never a real mutation) ---
        Tool(
            name="demo.simulated_action",
            capability="simulated_action",
            description=(
                "A simulated, non-destructive action used to demonstrate the "
                "confirmation flow. It never changes real infrastructure."
            ),
            provider="demo",
            read_only=False,
            permissions=["cloud.demo.write"],
            args_model=SimulatedActionArgs,
            handler=lambda args: demo.simulated_action(
                action=args.action, target=args.target
            ),
            availability=demo_avail,
        ),
    ]
    return ToolRegistry(tools)


_registry: ToolRegistry | None = None


def get_tool_registry() -> ToolRegistry:
    global _registry
    if _registry is None:
        _registry = build_tool_registry(get_settings(), get_provider_registry())
    return _registry


def reset_tool_registry() -> None:
    """Testing helper: drop the cached registry so settings changes apply."""
    global _registry
    _registry = None
