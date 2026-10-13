"""Application configuration loaded from environment variables.

All secrets are read from the environment. Nothing here should ever be
imported into the frontend. Every optional integration degrades gracefully
when its configuration is missing.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


def _split_csv(value: str | list[str]) -> list[str]:
    if isinstance(value, list):
        return [v.strip() for v in value if v.strip()]
    return [item.strip() for item in value.split(",") if item.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Core ---
    app_name: str = "Synthia"
    app_env: str = Field(default="development")
    port: int = Field(default=8000, ge=1, le=65535)
    # NoDecode keeps the raw string from env/.env so the validator below can
    # split a comma-separated list. Without it, pydantic-settings tries to
    # JSON-decode the value first and a plain CSV value raises SettingsError.
    cors_allowed_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]
    )
    api_auth_token: str | None = None
    demo_mode: bool = True
    allow_mutating: bool = False
    rate_limit_per_minute: int = Field(default=60, ge=0)
    max_request_chars: int = Field(default=8000, ge=1)
    max_log_lines: int = Field(default=200, ge=1, le=5000)

    # --- LLM ---
    llm_provider: str = "demo"  # demo | openai
    llm_api_key: str | None = None
    llm_model: str = "gpt-4o-mini"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_timeout_seconds: float = Field(default=45.0, gt=0)
    llm_max_tokens: int = Field(default=800, gt=0)

    # --- Speech to text (server-side, optional) ---
    stt_provider: str = "none"  # none | openai
    stt_api_key: str | None = None
    stt_model: str = "whisper-1"
    stt_base_url: str = "https://api.openai.com/v1"
    stt_timeout_seconds: float = Field(default=60.0, gt=0)
    stt_max_upload_bytes: int = Field(default=10 * 1024 * 1024, gt=0)

    # --- AWS ---
    aws_enabled: bool = False
    aws_default_region: str = "us-east-1"
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    aws_session_token: str | None = None

    # --- Docker (local) ---
    docker_enabled: bool = False
    docker_socket: str = "unix:///var/run/docker.sock"

    # --- Azure ---
    azure_enabled: bool = False
    azure_subscription_id: str | None = None

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def _parse_origins(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        text = value.strip()
        # Accept a JSON array too (e.g. '["https://a.com", "https://b.com"]').
        if text.startswith("["):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                pass
            else:
                if isinstance(parsed, list):
                    return [str(item).strip() for item in parsed if str(item).strip()]
        return _split_csv(text)

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in {"production", "prod"}

    @property
    def llm_configured(self) -> bool:
        return self.llm_provider != "demo" and bool(self.llm_api_key)

    @property
    def stt_configured(self) -> bool:
        return self.stt_provider != "none" and bool(self.stt_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
