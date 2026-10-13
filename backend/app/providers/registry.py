"""Provider registry: owns adapter instances and reports their status."""

from __future__ import annotations

from ..config import Settings, get_settings
from .aws_provider import AWSProvider
from .azure_provider import AzureProvider
from .base import CloudProvider, ProviderHealth
from .demo_provider import DemoProvider
from .docker_provider import DockerProvider


class ProviderRegistry:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._providers: dict[str, CloudProvider] = {
            "aws": AWSProvider(settings),
            "docker": DockerProvider(settings),
            "azure": AzureProvider(settings),
            "demo": DemoProvider(settings),
        }

    def get(self, provider_id: str) -> CloudProvider:
        return self._providers[provider_id]

    def ids(self) -> list[str]:
        return list(self._providers.keys())

    def health(self, provider_id: str) -> ProviderHealth:
        return self._providers[provider_id].health()

    def all_health(self) -> list[tuple[str, ProviderHealth]]:
        order = ["aws", "docker", "azure", "demo"]
        return [(pid, self._providers[pid].health()) for pid in order]


_registry: ProviderRegistry | None = None


def get_provider_registry() -> ProviderRegistry:
    global _registry
    if _registry is None:
        _registry = ProviderRegistry(get_settings())
    return _registry


def reset_provider_registry() -> None:
    global _registry
    _registry = None
