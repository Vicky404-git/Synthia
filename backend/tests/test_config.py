"""Configuration parsing tests, focused on env-based CORS parsing."""

from __future__ import annotations

import pytest

from app.config import Settings


def test_cors_defaults() -> None:
    settings = Settings()
    assert settings.cors_allowed_origins == [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]


def test_cors_csv_string() -> None:
    settings = Settings(
        cors_allowed_origins="http://localhost:5173,https://app.vercel.app"
    )
    assert settings.cors_allowed_origins == [
        "http://localhost:5173",
        "https://app.vercel.app",
    ]


def test_cors_json_array_string() -> None:
    settings = Settings(
        cors_allowed_origins='["https://a.example", "https://b.example"]'
    )
    assert settings.cors_allowed_origins == [
        "https://a.example",
        "https://b.example",
    ]


def test_cors_json_array_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "CORS_ALLOWED_ORIGINS", '["https://a.example","https://b.example"]'
    )
    # get_settings is lru_cached; construct directly to exercise the env source.
    settings = Settings()
    assert settings.cors_allowed_origins == [
        "https://a.example",
        "https://b.example",
    ]


def test_cors_single_value() -> None:
    settings = Settings(cors_allowed_origins="https://only.example")
    assert settings.cors_allowed_origins == ["https://only.example"]
