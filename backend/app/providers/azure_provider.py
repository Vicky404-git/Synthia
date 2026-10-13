"""Azure adapter (configuration model only, not implemented in V1).

This provider exists to prove the architecture is extensible. It is explicitly
reported as *planned / unconfigured* and never claims to be connected. No live
Azure operation is implemented or verified in this version.
"""

from __future__ import annotations

from ..config import Settings
from ..errors import ProviderNotConfiguredError
from ..schemas import ProviderStatus
from .base import CloudProvider, ProviderHealth, ProviderResult


class AzureProvider(CloudProvider):
    id = "azure"
    label = "Azure"
    read_only = True
    implemented = False

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def health(self) -> ProviderHealth:
        if not self._settings.azure_enabled:
            return ProviderHealth(
                status=ProviderStatus.disabled,
                detail="Azure integration is planned and disabled by default.",
                capabilities=[],
                setup_hint=(
                    "Azure support is on the roadmap. Set AZURE_ENABLED=true only "
                    "once an adapter is implemented."
                ),
            )
        return ProviderHealth(
            status=ProviderStatus.unconfigured,
            detail=(
                "Azure is enabled in configuration, but no live adapter is "
                "implemented or verified in this version."
            ),
            capabilities=[],
            setup_hint="Implement the Azure SDK adapter before enabling this.",
        )

    def capabilities(self) -> list[str]:
        return []

    def execute(self, operation: str, arguments: dict) -> ProviderResult:
        raise ProviderNotConfiguredError(
            "Azure operations are not implemented in this version.",
            details={"provider": self.id},
        )
