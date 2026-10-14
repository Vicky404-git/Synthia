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
    # "none" = disabled, "faster-whisper" = local CPU inference (default),
    # "openai" = hosted OpenAI-compatible Whisper endpoint.
    stt_provider: str = "faster-whisper"
    stt_api_key: str | None = None
    # Model name for the selected provider: a local size (tiny|base|small|
    # medium|large-v3) for faster-whisper, or a hosted name (whisper-1).
    stt_model: str = "base"
    stt_base_url: str = "https://api.openai.com/v1"
    stt_timeout_seconds: float = Field(default=60.0, gt=0)
    stt_max_upload_bytes: int = Field(default=10 * 1024 * 1024, gt=0)

    # --- Local Faster-Whisper (CPU, INT8 by default) ---
    stt_device: str = "cpu"  # cpu | cuda | auto
    stt_compute_type: str = "int8"  # int8 | int8_float16 | float16 | float32
    stt_cpu_threads: int = Field(default=0, ge=0)  # 0 = let CTranslate2 decide
    stt_num_workers: int = Field(default=1, ge=1)
    stt_beam_size: int = Field(default=1, ge=1)
    stt_vad_filter: bool = True
    # Where model files are cached. Kept outside the repository by default.
    stt_cache_dir: str | None = None
    # Local inference (including the very first model download) can be slow on
    # CPU, so it gets a more generous timeout than a hosted request.
    stt_local_timeout_seconds: float = Field(default=300.0, gt=0)

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
        provider = self.stt_provider.strip().lower().replace("_", "-")
        if provider in {"faster-whisper", "local"}:
            return True
        return provider != "none" and bool(self.stt_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
