"""Curated registry of bring-your-own-key (BYOK) LLM providers.

Only these provider ids are accepted. The browser selects an id; the server maps
it to the base URL below, so a caller can never point Synthia at an arbitrary
upstream host. Every entry exposes an OpenAI-compatible ``/chat/completions``
endpoint, which is why a single provider implementation covers all of them.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LLMProviderSpec:
    id: str
    label: str
    base_url: str


_PROVIDERS: tuple[LLMProviderSpec, ...] = (
    LLMProviderSpec("openai", "OpenAI", "https://api.openai.com/v1"),
    LLMProviderSpec(
        "gemini",
        "Google Gemini",
        "https://generativelanguage.googleapis.com/v1beta/openai/",
    ),
    LLMProviderSpec("groq", "Groq", "https://api.groq.com/openai/v1"),
    LLMProviderSpec("openrouter", "OpenRouter", "https://openrouter.ai/api/v1"),
    LLMProviderSpec("deepseek", "DeepSeek", "https://api.deepseek.com"),
    LLMProviderSpec("together", "Together AI", "https://api.together.xyz/v1"),
    LLMProviderSpec("mistral", "Mistral AI", "https://api.mistral.ai/v1"),
    LLMProviderSpec("xai", "xAI", "https://api.x.ai/v1"),
)

_BY_ID: dict[str, LLMProviderSpec] = {spec.id: spec for spec in _PROVIDERS}

# Upper bounds for request-scoped values supplied by the browser. These keep a
# malicious or buggy client from forcing huge allocations or log lines.
MAX_MODEL_CHARS = 200
MAX_API_KEY_CHARS = 4096


def all_provider_specs() -> tuple[LLMProviderSpec, ...]:
    return _PROVIDERS


def supported_provider_ids() -> list[str]:
    return [spec.id for spec in _PROVIDERS]


def get_provider_spec(provider_id: str) -> LLMProviderSpec | None:
    return _BY_ID.get(provider_id.strip().lower())


def chat_completions_url(base_url: str) -> str:
    """Append ``/chat/completions`` without dropping path components.

    Only trailing separators are removed, so internal path segments such as
    Gemini's ``/v1beta/openai/`` are preserved.
    """
    return f"{base_url.rstrip('/')}/chat/completions"
