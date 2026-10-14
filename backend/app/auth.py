"""Authentication and rate limiting for sensitive endpoints.

For a public demo the real infrastructure endpoints must not be reachable by
anyone who obtains the URL. When ``API_AUTH_TOKEN`` is configured, sensitive
endpoints require ``Authorization: Bearer <token>``. When it is *not* configured
the API is open, which is only acceptable for local development / demo mode.
"""

from __future__ import annotations

import hmac
import time
from collections import defaultdict, deque

from fastapi import Header, Request

from .config import get_settings
from .errors import RateLimitedError, UnauthorizedError


async def require_auth(authorization: str | None = Header(default=None)) -> None:
    settings = get_settings()
    if not settings.api_auth_token:
        return
    if not authorization or not authorization.lower().startswith("bearer "):
        raise UnauthorizedError("Missing bearer token for a protected endpoint.")
    token = authorization.split(" ", 1)[1].strip()
    if not hmac.compare_digest(token, settings.api_auth_token):
        raise UnauthorizedError("Invalid bearer token.")


def ensure_authorized(authorization: str | None) -> None:
    """Raise only when auth is enabled and the bearer token is missing/invalid.

    Used for conditional protection (e.g. general chat stays open, but cloud
    tool execution requires the token when one is configured).
    """
    settings = get_settings()
    if not settings.api_auth_token:
        return
    if not authorization or not authorization.lower().startswith("bearer "):
        raise UnauthorizedError("This operation requires an API token.")
    token = authorization.split(" ", 1)[1].strip()
    if not hmac.compare_digest(token, settings.api_auth_token):
        raise UnauthorizedError("Invalid bearer token.")


class SlidingWindowRateLimiter:
    """Tiny in-memory rate limiter. Good enough for a single-instance demo.

    This is intentionally not distributed; a multi-instance deployment would
    need Redis or a gateway-level limiter.
    """

    def __init__(self, per_minute: int) -> None:
        self.per_minute = per_minute
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> None:
        if self.per_minute <= 0:
            return
        now = time.monotonic()
        window = self._hits[key]
        while window and now - window[0] > 60.0:
            window.popleft()
        if len(window) >= self.per_minute:
            raise RateLimitedError(
                "Rate limit exceeded. Slow down and try again shortly.",
                details={"limit_per_minute": self.per_minute},
            )
        window.append(now)


_limiter: SlidingWindowRateLimiter | None = None


def get_rate_limiter() -> SlidingWindowRateLimiter:
    global _limiter
    if _limiter is None:
        _limiter = SlidingWindowRateLimiter(get_settings().rate_limit_per_minute)
    return _limiter


def reset_rate_limiter() -> None:
    global _limiter
    _limiter = None


def client_key(request: Request) -> str:
    if request.client and request.client.host:
        return request.client.host
    return "unknown"
