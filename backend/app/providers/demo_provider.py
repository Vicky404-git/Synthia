"""Demo provider.

Serves clearly labelled sample data so the application can be demonstrated
without any cloud credentials. Every result is marked ``simulated=True`` and
carries an explicit "DEMO DATA" message. It never performs a real mutation.
"""

from __future__ import annotations

from ..config import Settings
from ..schemas import ProviderStatus
from .base import CloudProvider, ProviderHealth, ProviderResult

_DEMO_EC2 = [
    {
        "id": "i-0demo1234567890a",
        "name": "web-prod-01",
        "type": "t3.medium",
        "state": "running",
        "az": "us-east-1a",
        "private_ip": "10.0.1.21",
        "public_ip": "203.0.113.10",
    },
    {
        "id": "i-0demo1234567890b",
        "name": "worker-02",
        "type": "t3.small",
        "state": "stopped",
        "az": "us-east-1b",
        "private_ip": "10.0.2.34",
        "public_ip": None,
    },
]

_DEMO_BUCKETS = [
    {"name": "synthia-demo-assets", "creation_date": "2024-01-15T09:30:00Z"},
    {"name": "class-project-logs", "creation_date": "2024-03-02T14:05:00Z"},
]

_DEMO_CONTAINERS = [
    {
        "id": "d3m0c0nta1n",
        "name": "synthia-api",
        "image": "synthia/backend:latest",
        "state": "running",
        "status": "Up 2 hours",
    },
    {
        "id": "d3m0c0nta2n",
        "name": "synthia-web",
        "image": "synthia/frontend:latest",
        "state": "exited",
        "status": "Exited (0) 12 minutes ago",
    },
]


class DemoProvider(CloudProvider):
    id = "demo"
    label = "Demo"
    read_only = True

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def health(self) -> ProviderHealth:
        return ProviderHealth(
            status=ProviderStatus.demo,
            detail="Demo provider active. All data below is simulated sample data.",
            capabilities=self.capabilities(),
            setup_hint=(
                "Configure a real provider (AWS/Docker) for live infrastructure."
            ),
        )

    def capabilities(self) -> list[str]:
        return [
            "List sample EC2 instances",
            "List sample S3 buckets",
            "List sample containers",
            "Simulated safe action (never a real mutation)",
        ]

    def list_ec2_instances(self, region: str | None = None) -> ProviderResult:
        return ProviderResult(
            data={
                "region": region or "us-east-1",
                "count": len(_DEMO_EC2),
                "instances": [dict(item) for item in _DEMO_EC2],
            },
            provider=self.id,
            simulated=True,
            message="DEMO DATA — simulated EC2 instances, not a live AWS response.",
        )

    def describe_instance(self, instance_id: str) -> ProviderResult:
        for instance in _DEMO_EC2:
            if instance["id"] == instance_id:
                return ProviderResult(
                    data=dict(instance),
                    provider=self.id,
                    simulated=True,
                    message="DEMO DATA — simulated instance details.",
                )
        return ProviderResult(
            data={"id": instance_id, "state": "not-found"},
            provider=self.id,
            simulated=True,
            message="DEMO DATA — no matching simulated instance.",
        )

    def list_s3_buckets(self) -> ProviderResult:
        return ProviderResult(
            data={"count": len(_DEMO_BUCKETS), "buckets": [dict(b) for b in _DEMO_BUCKETS]},
            provider=self.id,
            simulated=True,
            message="DEMO DATA — simulated S3 buckets, not a live AWS response.",
        )

    def list_containers(self, all: bool = False) -> ProviderResult:
        items = _DEMO_CONTAINERS if all else [
            c for c in _DEMO_CONTAINERS if c["state"] == "running"
        ]
        return ProviderResult(
            data={"count": len(items), "containers": [dict(c) for c in items]},
            provider=self.id,
            simulated=True,
            message="DEMO DATA — simulated containers, not a live Docker daemon.",
        )

    def inspect_container(self, container_id: str) -> ProviderResult:
        for container in _DEMO_CONTAINERS:
            if container["id"] == container_id or container["name"] == container_id:
                return ProviderResult(
                    data=dict(container),
                    provider=self.id,
                    simulated=True,
                    message="DEMO DATA — simulated container details.",
                )
        return ProviderResult(
            data={"id": container_id, "state": "not-found"},
            provider=self.id,
            simulated=True,
            message="DEMO DATA — no matching simulated container.",
        )

    def container_logs(self, container_id: str, tail: int = 50) -> ProviderResult:
        lines = [
            "[DEMO DATA] simulated log output",
            f"[DEMO DATA] container={container_id}",
            "[DEMO DATA] this is not real container output",
        ]
        return ProviderResult(
            data={"id": container_id, "tail": tail, "lines": lines},
            provider=self.id,
            simulated=True,
            message="DEMO DATA — simulated container logs.",
        )

    def simulated_action(self, action: str = "noop", target: str = "demo") -> ProviderResult:
        return ProviderResult(
            data={"action": action, "target": target, "performed": False},
            provider=self.id,
            simulated=True,
            message=(
                "DEMO — this is a simulated, non-destructive action. "
                "No real infrastructure was changed."
            ),
        )
