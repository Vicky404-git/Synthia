"""Shared test fixtures.

Tests never touch real cloud resources. Provider behaviour is exercised with
mocks, and the default configuration runs in demo mode with rate limiting
disabled.
"""

from __future__ import annotations

import os

import pytest

# Baseline environment for the suite (set before any Settings is constructed).
os.environ["RATE_LIMIT_PER_MINUTE"] = "0"
os.environ["DEMO_MODE"] = "true"
os.environ.setdefault("APP_ENV", "test")


def _reset_caches() -> None:
    from app.auth import reset_rate_limiter
    from app.config import get_settings
    from app.lex import reset_lex_provider
    from app.providers.registry import reset_provider_registry
    from app.store import reset_transcription_store
    from app.tools.registry import reset_tool_registry

    get_settings.cache_clear()
    reset_provider_registry()
    reset_tool_registry()
    reset_rate_limiter()
    reset_transcription_store()
    reset_lex_provider()


@pytest.fixture
def make_client(monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import create_app

    def _factory(**env: str):
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        _reset_caches()
        return TestClient(create_app())

    _reset_caches()
    return _factory


@pytest.fixture
def client(make_client):
    return make_client()
