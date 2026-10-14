"""Optional, replaceable voice-command intent provider.

The default is a clearly labelled simulated provider so the command flow works
offline. When ``LEX_ENABLED`` and a bot id are configured, the AWS Lex V2
adapter is used instead. Application code depends only on :class:`LexProvider`,
so this can later be swapped for a fully local intent recogniser without
changing the routes or the frontend.
"""

from __future__ import annotations

from ..config import get_settings
from .aws_lex import AWSLexProvider
from .base import LexHealth, LexIntentResult, LexProvider, resolve_session_id
from .mock import MockLexProvider

__all__ = [
    "AWSLexProvider",
    "LexHealth",
    "LexIntentResult",
    "LexProvider",
    "MockLexProvider",
    "get_lex_provider",
    "reset_lex_provider",
    "resolve_session_id",
]

_provider: LexProvider | None = None


def get_lex_provider() -> LexProvider:
    global _provider
    if _provider is None:
        settings = get_settings()
        if settings.lex_enabled and settings.lex_bot_id:
            _provider = AWSLexProvider(settings)
        else:
            _provider = MockLexProvider(settings)
    return _provider


def reset_lex_provider() -> None:
    global _provider
    _provider = None
