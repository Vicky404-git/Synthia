"""Request-scoped bring-your-own-key (BYOK) LLM configuration.

The browser may send three headers — on the chat endpoints *only* — to select a
provider, model and API key for that single request:

    X-Synthia-LLM-Provider
    X-Synthia-LLM-Model
    X-Synthia-LLM-API-Key

* All three present and valid -> a request-scoped provider is built from the
  curated registry. The key is used only to construct that object; it is never
  stored, logged, returned, or placed in error details.
* None present -> the server-configured default/demo provider is used.
* Anything in between (partial, unknown provider, empty/whitespace, oversized)
  -> a structured ``invalid_llm_config`` error. Synthia never silently falls
  back to the default provider when the user asked for a specific one.

This module deliberately contains no ``get_llm_provider`` import so it can be
imported from the package ``__init__`` without a cycle.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from ..config import Settings
from ..errors import InvalidLLMConfigError
from .base import LLMProvider
from .openai_compatible import OpenAICompatibleLLMProvider
from .providers import (
    MAX_API_KEY_CHARS,
    MAX_MODEL_CHARS,
    all_provider_specs,
    get_provider_spec,
    supported_provider_ids,
)

logger = logging.getLogger(__name__)
HEADER_PROVIDER = "X-Synthia-LLM-Provider"
HEADER_MODEL = "X-Synthia-LLM-Model"
HEADER_API_KEY = "X-Synthia-LLM-API-Key"

_REQUIRED = {
    "provider": HEADER_PROVIDER,
    "model": HEADER_MODEL,
    "api_key": HEADER_API_KEY,
}


@dataclass(frozen=True)
class LLMRequestConfig:
    provider_id: str
    model: str
    api_key: str


def _header_values(headers: Any, name: str) -> list[str]:
    """Return all values for ``name`` (case-insensitively).

    Supports Starlette ``Headers`` (``getlist``) and plain mappings so the logic
    is trivially unit-testable.
    """
    if headers is None:
        return []
    try:
        # Avoid logging raw header contents
        if hasattr(headers, "getlist"):
            return list(headers.getlist(name))
    except Exception:
        pass
    lowered = name.lower()
    values: list[str] = []
    try:
        for key, value in dict(headers).items():
            if str(key).lower() == lowered:
                if isinstance(value, (list, tuple)):
                    values.extend(str(item) for item in value)
                else:
                    values.append(str(value))
    except Exception:
        pass
    return values


def _single(headers: Any, name: str) -> str | None:
    values = _header_values(headers, name)
    if not values:
        return None
    if len(values) > 1:
        raise InvalidLLMConfigError(
            "Duplicate LLM configuration headers are not allowed.",
            details={"header": name},
        )
    return values[0]


def parse_byok_headers(headers: Any) -> LLMRequestConfig | None:
    """Parse and validate the BYOK headers.

    Returns ``None`` when no BYOK header is present. Raises
    ``InvalidLLMConfigError`` for any partial or malformed configuration.
    """
    raw = {field: _single(headers, name) for field, name in _REQUIRED.items()}

    # A header that is simply absent (None) is different from one sent empty.
    if all(value is None for value in raw.values()):
        return None

    missing = [
        field
        for field, value in raw.items()
        if value is None or not value.strip()
    ]
    if missing:
        raise InvalidLLMConfigError(
            "The requested LLM configuration is incomplete.",
            details={"missing": missing},
        )

    assert raw["provider"] is not None  # for type checkers
    assert raw["model"] is not None
    assert raw["api_key"] is not None

    provider_id = raw["provider"].strip().lower()
    spec = get_provider_spec(provider_id)
    if spec is None:
        raise InvalidLLMConfigError(
            "Unknown LLM provider.",
            details={
                "provider": provider_id,
                "supported": supported_provider_ids(),
            },
        )

    model = raw["model"].strip()
    if len(model) > MAX_MODEL_CHARS:
        raise InvalidLLMConfigError(
            "The model ID is too long.",
            details={"max_model_chars": MAX_MODEL_CHARS},
        )

    api_key = raw["api_key"].strip()
    if len(api_key) > MAX_API_KEY_CHARS:
        raise InvalidLLMConfigError(
            "The API key is too long.",
            details={"max_api_key_chars": MAX_API_KEY_CHARS},
        )

    return LLMRequestConfig(provider_id=spec.id, model=model, api_key=api_key)


def build_provider(config: LLMRequestConfig, settings: Settings) -> LLMProvider:
    spec = get_provider_spec(config.provider_id)
    if spec is None:  # pragma: no cover - guarded by parse_byok_headers
        raise InvalidLLMConfigError(
            "Unknown LLM provider.",
            details={"supported": supported_provider_ids()},
        )
    return OpenAICompatibleLLMProvider(
        settings,
        provider_id=spec.id,
        base_url=spec.base_url,
        model=config.model,
        api_key=config.api_key,
    )


def describe_providers() -> list[dict[str, str]]:
    """Registry as plain data (id/label only — never keys or base URLs)."""
    return [{"id": spec.id, "label": spec.label} for spec in all_provider_specs()]
