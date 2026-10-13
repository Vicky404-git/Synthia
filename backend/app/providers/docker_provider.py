"""Docker adapter (read-only, local development only).

This adapter talks to the local Docker daemon through the Docker SDK. It is
intended for the developer's own machine / demo. The host Docker socket must
never be exposed through the public deployment, so the adapter reports itself
as disabled in production environments.
"""

from __future__ import annotations

from typing import Any

from ..config import Settings
from ..errors import ProviderError, ProviderNotConfiguredError
from ..schemas import ProviderStatus
from .base import CloudProvider, ProviderHealth, ProviderResult


class DockerProvider(CloudProvider):
    id = "docker"
    label = "Docker"
    read_only = True

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _blocked_in_production(self) -> bool:
        return self._settings.is_production

    def health(self) -> ProviderHealth:
        if not self._settings.docker_enabled:
            return ProviderHealth(
                status=ProviderStatus.disabled,
                detail="Docker integration is disabled (set DOCKER_ENABLED=true).",
                capabilities=self.capabilities(),
                setup_hint=(
                    "Only enable on a trusted local machine with the Docker "
                    "socket reachable."
                ),
            )
        if self._blocked_in_production():
            return ProviderHealth(
                status=ProviderStatus.disabled,
                detail=(
                    "Docker access is disabled in production for safety. Run the "
                    "Docker integration locally for the demonstration."
                ),
                capabilities=self.capabilities(),
            )
        try:
            client = self._client()
            client.ping()
        except ProviderNotConfiguredError as exc:
            return ProviderHealth(
                status=ProviderStatus.unconfigured,
                detail=exc.message,
                capabilities=self.capabilities(),
                setup_hint="Install the Docker SDK and make the socket reachable.",
            )
        except Exception as exc:  # noqa: BLE001 - report any daemon error safely
            return ProviderHealth(
                status=ProviderStatus.error,
                detail=f"Docker daemon not reachable: {type(exc).__name__}.",
                capabilities=self.capabilities(),
                setup_hint=f"Check DOCKER_SOCKET ({self._settings.docker_socket}).",
            )
        return ProviderHealth(
            status=ProviderStatus.connected,
            detail="Local Docker daemon reachable (read-only).",
            capabilities=self.capabilities(),
        )

    def capabilities(self) -> list[str]:
        return [
            "List containers",
            "Inspect a container",
            f"Read container logs (max {self._settings.max_log_lines} lines)",
        ]

    def _client(self) -> Any:
        if not self._settings.docker_enabled or self._blocked_in_production():
            raise ProviderNotConfiguredError(
                "Docker integration is not available in this environment.",
                details={"provider": self.id},
            )
        try:
            import docker  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover - depends on env
            raise ProviderNotConfiguredError(
                "The docker Python SDK is not installed.",
                details={"provider": self.id},
            ) from exc
        return docker.DockerClient(base_url=self._settings.docker_socket, timeout=5)

    @staticmethod
    def _map_error(exc: Exception, what: str) -> ProviderError:
        try:
            import docker  # noqa: PLC0415

            if isinstance(exc, docker.errors.NotFound):
                return ProviderError(
                    "No such container.", details={"provider": "docker"}, status_code=404
                )
            if isinstance(exc, docker.errors.APIError):
                return ProviderError(
                    f"Docker refused the request to {what}.",
                    details={"provider": "docker"},
                )
        except ImportError:  # pragma: no cover
            pass
        return ProviderError(
            f"Could not {what}.", details={"provider": "docker"}
        )

    def list_containers(self, all: bool = False) -> ProviderResult:
        client = self._client()
        try:
            containers = client.containers.list(all=all)
        except Exception as exc:  # noqa: BLE001
            raise self._map_error(exc, "list containers") from exc
        items = []
        for container in containers:
            items.append(
                {
                    "id": container.short_id,
                    "name": container.name,
                    "image": _image_name(container),
                    "state": container.status,
                    "status": container.status,
                }
            )
        return ProviderResult(
            data={"count": len(items), "containers": items},
            provider=self.id,
            message=f"Found {len(items)} container(s).",
        )

    def inspect_container(self, container_id: str) -> ProviderResult:
        client = self._client()
        try:
            container = client.containers.get(container_id)
            attrs = container.attrs
        except Exception as exc:  # noqa: BLE001
            raise self._map_error(exc, f"inspect container {container_id}") from exc
        state = attrs.get("State", {})
        config = attrs.get("Config", {})
        return ProviderResult(
            data={
                "id": attrs.get("Id", "")[:12],
                "name": attrs.get("Name", "").lstrip("/"),
                "image": config.get("Image"),
                "state": state.get("Status"),
                "started_at": state.get("StartedAt"),
                "restart_count": attrs.get("RestartCount"),
                "env_keys": sorted(
                    item.split("=", 1)[0] for item in (config.get("Env") or [])
                ),
            },
            provider=self.id,
            message=f"Container {container_id} inspected.",
        )

    def container_logs(self, container_id: str, tail: int = 50) -> ProviderResult:
        bounded = max(1, min(int(tail), self._settings.max_log_lines))
        client = self._client()
        try:
            container = client.containers.get(container_id)
            raw = container.logs(tail=bounded, timestamps=False)
        except Exception as exc:  # noqa: BLE001
            raise self._map_error(exc, f"read logs for {container_id}") from exc
        text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
        lines = text.splitlines()[-bounded:]
        return ProviderResult(
            data={
                "id": container_id,
                "tail": bounded,
                "lines": lines,
            },
            provider=self.id,
            message=f"Returned {len(lines)} log line(s).",
        )


def _image_name(container: Any) -> str:
    tags = getattr(container.image, "tags", None)
    if tags:
        return tags[0]
    return getattr(container.image, "short_id", "unknown")
