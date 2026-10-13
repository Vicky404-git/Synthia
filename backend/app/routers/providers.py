"""Provider configuration and connection status (no secrets exposed)."""

from __future__ import annotations

from fastapi import APIRouter

from ..config import get_settings
from ..providers import get_provider_registry
from ..schemas import ProviderInfo, ProviderListResponse

router = APIRouter(prefix="/api", tags=["providers"])


@router.get("/providers", response_model=ProviderListResponse)
async def list_providers() -> ProviderListResponse:
    settings = get_settings()
    registry = get_provider_registry()
    providers: list[ProviderInfo] = []
    for provider_id, health in registry.all_health():
        provider = registry.get(provider_id)
        providers.append(
            ProviderInfo(
                id=provider_id,
                label=provider.label,
                status=health.status,
                read_only=provider.read_only,
                detail=health.detail,
                capabilities=health.capabilities,
                setup_hint=health.setup_hint,
            )
        )
    mode = "demo" if settings.demo_mode else settings.app_env
    return ProviderListResponse(mode=mode, providers=providers)
