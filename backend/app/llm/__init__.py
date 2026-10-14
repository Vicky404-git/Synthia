"""LLM provider abstraction, registry and request-scoped resolution."""

from __future__ import annotations

from typing import Any

from ..config import get_settings
from .base import LLMProvider, LLMResult
from .byok import (
    HEADER_API_KEY,
    HEADER_MODEL,
    HEADER_PROVIDER,
    LLMRequestConfig,
    build_provider,
    describe_providers,
    parse_byok_headers,
)
from .demo import DemoLLMProvider
from .openai_compatible import OpenAICompatibleLLMProvider
from .providers import (
    LLMProviderSpec,
    all_provider_specs,
    chat_completions_url,
    get_provider_spec,
    supported_provider_ids,
)


def get_llm_provider() -> LLMProvider:
    """The server-configured default provider (demo unless a key is set)."""
    settings = get_settings()
    if settings.llm_provider == "openai" and settings.llm_api_key:
        return OpenAICompatibleLLMProvider(settings)
    return DemoLLMProvider(settings)


def resolve_llm_provider(request: Any = None) -> LLMProvider:
    """Resolve the provider for a single request.

    BYOK headers (if any) select the provider for this request only; otherwise
    the server-configured default is used. The resolved instance is reused for
    the whole request lifecycle (intent interpretation and answer generation).
    """
    headers = getattr(request, "headers", None) if request is not None else None
    config = parse_byok_headers(headers)
    if config is None:
        return get_llm_provider()
    return build_provider(config, get_settings())


__all__ = [
    "HEADER_API_KEY",
    "HEADER_MODEL",
    "HEADER_PROVIDER",
    "LLMProvider",
    "LLMProviderSpec",
    "LLMRequestConfig",
    "LLMResult",
    "all_provider_specs",
    "build_provider",
    "chat_completions_url",
    "describe_providers",
    "get_llm_provider",
    "get_provider_spec",
    "parse_byok_headers",
    "resolve_llm_provider",
    "supported_provider_ids",
]
