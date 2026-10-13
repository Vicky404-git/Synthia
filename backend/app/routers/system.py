"""Health and readiness endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from .. import __version__
from ..config import get_settings
from ..llm import get_llm_provider
from ..providers import get_provider_registry
from ..schemas import DependencyStatus, HealthResponse, ReadyResponse
from ..stt import get_stt_provider

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(status="ok", service=settings.app_name, version=__version__)


@router.get("/ready", response_model=ReadyResponse)
async def ready() -> ReadyResponse:
    settings = get_settings()
    llm = get_llm_provider()
    stt = get_stt_provider()
    registry = get_provider_registry()

    dependencies = [
        DependencyStatus(
            name="llm",
            ready=True,
            detail=(
                f"provider={llm.id} model={llm.model}"
                if settings.llm_configured
                else "demo provider (no API key configured)"
            ),
        ),
        DependencyStatus(
            name="stt",
            ready=stt.available,
            detail=(
                f"server-side STT: {stt.id}"
                if stt.available
                else "browser Web Speech API / typed input only"
            ),
        ),
    ]
    for provider_id, health in registry.all_health():
        dependencies.append(
            DependencyStatus(
                name=f"provider:{provider_id}",
                ready=health.status.value in {"connected", "demo"},
                detail=f"{health.status.value} — {health.detail}",
            )
        )

    ready_flag = True
    return ReadyResponse(
        ready=ready_flag,
        service=settings.app_name,
        version=__version__,
        environment=settings.app_env,
        demo_mode=settings.demo_mode,
        dependencies=dependencies,
    )
