"""LLM provider abstraction and factory."""

from __future__ import annotations

from ..config import get_settings
from .base import LLMProvider, LLMResult
from .demo import DemoLLMProvider
from .openai_compatible import OpenAICompatibleLLMProvider


def get_llm_provider() -> LLMProvider:
    settings = get_settings()
    if settings.llm_provider == "openai" and settings.llm_api_key:
        return OpenAICompatibleLLMProvider(settings)
    return DemoLLMProvider(settings)


__all__ = ["LLMProvider", "LLMResult", "get_llm_provider"]
