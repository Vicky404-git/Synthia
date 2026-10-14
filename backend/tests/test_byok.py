"""Request-scoped BYOK (bring-your-own-key) LLM configuration.

Upstream HTTP is always mocked, so no real provider is contacted and no real
key is used. A sentinel value lets us assert the key never leaks into a response
or an error payload.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import pytest
from starlette.datastructures import Headers

from app.config import Settings
from app.errors import InvalidLLMConfigError
from app.llm import (
    all_provider_specs,
    build_provider,
    chat_completions_url,
    parse_byok_headers,
    resolve_llm_provider,
)

SENTINEL = "sk-secret-byok-value-DO-NOT-LEAK"

# Capture the *real* httpx client class before any fixture patches the LLM's
# upstream client, so the HTTP-level test can still drive the app over ASGI.
_REAL_ASYNC_CLIENT = httpx.AsyncClient

EXPECTED_URLS = {
    "openai": "https://api.openai.com/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "groq": "https://api.groq.com/openai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "deepseek": "https://api.deepseek.com",
    "together": "https://api.together.xyz/v1",
    "mistral": "https://api.mistral.ai/v1",
    "xai": "https://api.x.ai/v1",
}


# --- Mock upstream ---------------------------------------------------------


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict | None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self) -> Any:
        return self._payload


class _FakeStreamResponse:
    def __init__(self, status_code: int, lines: list[str], text: str = "") -> None:
        self.status_code = status_code
        self._lines = lines
        self.text = text

    async def aread(self) -> bytes:
        return self.text.encode()

    async def aiter_lines(self):
        for line in self._lines:
            yield line


class _FakeStream:
    def __init__(self, response: _FakeStreamResponse) -> None:
        self._response = response

    async def __aenter__(self) -> _FakeStreamResponse:
        return self._response

    async def __aexit__(self, *exc: object) -> bool:
        return False


class FakeAsyncClient:
    """Records every upstream call and returns canned OpenAI-shaped responses."""

    calls: list[dict] = []
    reply_content = '{"operation": "conversation", "answer": "hello from byok"}'
    status_code = 200
    error_text = ""

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    async def __aenter__(self) -> FakeAsyncClient:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def post(self, url: str, headers=None, json=None):  # noqa: A002
        # Yield once so concurrent requests genuinely interleave their upstream
        # calls instead of running strictly sequentially.
        await asyncio.sleep(0)
        FakeAsyncClient.calls.append(
            {"url": url, "headers": dict(headers or {}), "json": json}
        )
        payload = {
            "choices": [{"message": {"content": FakeAsyncClient.reply_content}}],
            "model": (json or {}).get("model"),
            "usage": {"total_tokens": 1},
        }
        return _FakeResponse(
            FakeAsyncClient.status_code, payload, FakeAsyncClient.error_text
        )

    def stream(self, method: str, url: str, headers=None, json=None):  # noqa: A002
        FakeAsyncClient.calls.append(
            {"url": url, "headers": dict(headers or {}), "json": json}
        )
        lines = [
            'data: {"choices":[{"delta":{"content":"Hel"}}]}',
            'data: {"choices":[{"delta":{"content":"lo"}}]}',
            "data: [DONE]",
        ]
        return _FakeStream(
            _FakeStreamResponse(
                FakeAsyncClient.status_code, lines, FakeAsyncClient.error_text
            )
        )


@pytest.fixture
def fake_upstream(monkeypatch):
    from app.llm import openai_compatible

    FakeAsyncClient.calls = []
    FakeAsyncClient.reply_content = (
        '{"operation": "conversation", "answer": "hello from byok"}'
    )
    FakeAsyncClient.status_code = 200
    FakeAsyncClient.error_text = ""
    monkeypatch.setattr(openai_compatible.httpx, "AsyncClient", FakeAsyncClient)
    yield FakeAsyncClient
    FakeAsyncClient.calls = []


class _FakeRequest:
    def __init__(self, headers: Headers) -> None:
        self.headers = headers


def _byok(provider: str, model: str = "some-model", key: str = SENTINEL) -> dict:
    return {
        "X-Synthia-LLM-Provider": provider,
        "X-Synthia-LLM-Model": model,
        "X-Synthia-LLM-API-Key": key,
    }


# --- Registry / URL construction -------------------------------------------


def test_registry_contains_the_eight_providers_with_expected_urls():
    assert {spec.id: spec.base_url for spec in all_provider_specs()} == EXPECTED_URLS


def test_chat_completions_url_preserves_path_components():
    assert (
        chat_completions_url("https://api.openai.com/v1")
        == "https://api.openai.com/v1/chat/completions"
    )
    # The trailing slash must be collapsed but the /v1beta/openai path kept.
    assert (
        chat_completions_url(
            "https://generativelanguage.googleapis.com/v1beta/openai/"
        )
        == "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    )


def test_every_provider_builds_with_its_own_model_and_key():
    settings = Settings(rate_limit_per_minute=0)
    for spec in all_provider_specs():
        config = parse_byok_headers(
            Headers(_byok(spec.id, model=f"model-{spec.id}", key=f"key-{spec.id}"))
        )
        assert config is not None
        provider = build_provider(config, settings)
        assert provider.id == spec.id
        assert provider.model == f"model-{spec.id}"


# --- Header parsing / validation -------------------------------------------


def test_absent_headers_use_the_default_provider():
    assert parse_byok_headers(None) is None
    assert parse_byok_headers(Headers({})) is None


def test_partial_profile_is_rejected():
    with pytest.raises(InvalidLLMConfigError) as exc:
        parse_byok_headers(
            Headers({"X-Synthia-LLM-Provider": "groq", "X-Synthia-LLM-Model": "m"})
        )
    assert "api_key" in exc.value.details["missing"]


def test_whitespace_only_values_are_rejected():
    with pytest.raises(InvalidLLMConfigError):
        parse_byok_headers(
            Headers(
                {
                    "X-Synthia-LLM-Provider": "groq",
                    "X-Synthia-LLM-Model": "m",
                    "X-Synthia-LLM-API-Key": "   ",
                }
            )
        )


def test_duplicate_headers_are_rejected():
    headers = Headers(
        raw=[
            (b"x-synthia-llm-provider", b"groq"),
            (b"x-synthia-llm-provider", b"openai"),
        ]
    )
    with pytest.raises(InvalidLLMConfigError):
        parse_byok_headers(headers)


def test_oversized_model_and_key_are_rejected():
    with pytest.raises(InvalidLLMConfigError):
        parse_byok_headers(Headers(_byok("groq", model="x" * 201)))
    with pytest.raises(InvalidLLMConfigError):
        parse_byok_headers(Headers(_byok("groq", key="k" * 4097)))


def test_arbitrary_upstream_url_is_rejected():
    # There is no URL header; a URL smuggled into the provider field is unknown.
    with pytest.raises(InvalidLLMConfigError):
        parse_byok_headers(Headers(_byok("https://evil.example/v1")))


# --- HTTP level: normal chat -----------------------------------------------


def test_byok_profile_is_used_for_a_normal_chat(make_client, fake_upstream):
    client = make_client()
    response = client.post(
        "/api/chat",
        headers=_byok("groq", model="llama-3.1-8b-instant"),
        json={"message": "hello", "mode": "general"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["provider_used"] == "groq"
    assert SENTINEL not in response.text

    call = fake_upstream.calls[-1]
    assert call["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert call["headers"]["Authorization"] == f"Bearer {SENTINEL}"
    assert call["json"]["model"] == "llama-3.1-8b-instant"


def test_no_headers_falls_back_to_demo(client):
    response = client.post(
        "/api/chat", json={"message": "hello", "mode": "general"}
    )
    assert response.status_code == 200
    assert response.json()["provider_used"] == "demo"


def test_byok_profile_is_used_for_streaming(make_client, fake_upstream):
    client = make_client()
    response = client.post(
        "/api/chat/stream",
        headers=_byok("openrouter", model="meta-llama/llama-3-8b"),
        json={"message": "hello", "mode": "general"},
    )
    assert response.status_code == 200
    assert "Hel" in response.text and "lo" in response.text
    assert '"provider_used": "openrouter"' in response.text
    assert SENTINEL not in response.text
    assert (
        fake_upstream.calls[-1]["headers"]["Authorization"] == f"Bearer {SENTINEL}"
    )


# --- HTTP level: validation errors -----------------------------------------


def test_unknown_provider_returns_structured_error(client):
    response = client.post(
        "/api/chat",
        headers=_byok("evil"),
        json={"message": "hello", "mode": "general"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_llm_config"
    assert SENTINEL not in response.text


def test_partial_profile_returns_structured_error(client):
    response = client.post(
        "/api/chat",
        headers={"X-Synthia-LLM-Provider": "groq", "X-Synthia-LLM-Model": "m"},
        json={"message": "hello", "mode": "general"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_llm_config"


def test_streaming_reports_invalid_profile_as_sse_error(make_client, fake_upstream):
    client = make_client()
    response = client.post(
        "/api/chat/stream",
        headers=_byok("evil"),
        json={"message": "hello", "mode": "general"},
    )
    assert response.status_code == 200
    assert '"code": "invalid_llm_config"' in response.text
    assert SENTINEL not in response.text


# --- Secret handling --------------------------------------------------------


def test_upstream_error_message_is_redacted(make_client, fake_upstream):
    fake_upstream.status_code = 500
    fake_upstream.error_text = f'{{"error": "rejected key {SENTINEL}"}}'
    client = make_client()
    response = client.post(
        "/api/chat",
        headers=_byok("mistral"),
        json={"message": "hello", "mode": "general"},
    )
    assert response.status_code == 502
    assert SENTINEL not in response.text
    assert "***" in response.text


def test_byok_does_not_bypass_infrastructure_authorization(
    make_client, fake_upstream
):
    fake_upstream.reply_content = json.dumps(
        {
            "operation": "read_only",
            "tool": "demo.list_ec2_instances",
            "arguments": {},
        }
    )
    client = make_client(API_AUTH_TOKEN="s3cret")
    response = client.post(
        "/api/chat",
        headers=_byok("groq"),
        json={"message": "list my ec2 instances", "mode": "cloud"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


# --- Isolation --------------------------------------------------------------


async def test_concurrent_byok_requests_stay_isolated(fake_upstream):
    request_a = _FakeRequest(
        Headers(_byok("openai", model="gpt-4o-mini", key="key-a"))
    )
    request_b = _FakeRequest(Headers(_byok("xai", model="grok-2", key="key-b")))

    provider_a = resolve_llm_provider(request_a)
    provider_b = resolve_llm_provider(request_b)

    assert (provider_a.id, provider_a.model) == ("openai", "gpt-4o-mini")
    assert (provider_b.id, provider_b.model) == ("xai", "grok-2")
    assert provider_a is not provider_b

    results = await asyncio.gather(
        provider_a.complete([{"role": "user", "content": "a"}]),
        provider_b.complete([{"role": "user", "content": "b"}]),
    )
    assert [result.provider for result in results] == ["openai", "xai"]

    auths = {call["headers"]["Authorization"] for call in fake_upstream.calls}
    assert auths == {"Bearer key-a", "Bearer key-b"}
    models = {call["json"]["model"] for call in fake_upstream.calls}
    assert models == {"gpt-4o-mini", "grok-2"}


async def test_concurrent_http_requests_keep_their_own_provider(
    make_client, fake_upstream
):
    """Two simultaneous /api/chat calls must not bleed provider/key into one another.

    The upstream HTTP client is mocked, so each request is captured with its URL,
    model and Authorization header. No real provider or key is contacted.
    """
    app = make_client().app
    transport = httpx.ASGITransport(app=app)
    async with _REAL_ASYNC_CLIENT(
        transport=transport, base_url="http://testserver"
    ) as http:
        response_a, response_b = await asyncio.gather(
            http.post(
                "/api/chat",
                headers=_byok("openai", model="gpt-4o-mini", key="key-a"),
                json={"message": "hello from a", "mode": "general"},
            ),
            http.post(
                "/api/chat",
                headers=_byok("xai", model="grok-2", key="key-b"),
                json={"message": "hello from b", "mode": "general"},
            ),
        )

    assert response_a.status_code == 200
    assert response_b.status_code == 200
    # Each response reports the provider its own headers selected.
    assert response_a.json()["provider_used"] == "openai"
    assert response_b.json()["provider_used"] == "xai"

    # Correlate the captured upstream calls by their Authorization header.
    by_auth = {call["headers"]["Authorization"]: call for call in fake_upstream.calls}
    assert set(by_auth) == {"Bearer key-a", "Bearer key-b"}
    assert by_auth["Bearer key-a"]["url"] == (
        "https://api.openai.com/v1/chat/completions"
    )
    assert by_auth["Bearer key-a"]["json"]["model"] == "gpt-4o-mini"
    assert by_auth["Bearer key-b"]["url"] == "https://api.x.ai/v1/chat/completions"
    assert by_auth["Bearer key-b"]["json"]["model"] == "grok-2"
    assert SENTINEL not in response_a.text
    assert SENTINEL not in response_b.text


def test_headers_are_case_insensitive():
    config = parse_byok_headers(
        Headers(
            {
                "x-synthia-llm-provider": "deepseek",
                "x-synthia-llm-model": "deepseek-chat",
                "x-synthia-llm-api-key": "k",
            }
        )
    )
    assert config is not None
    assert config.provider_id == "deepseek"
    assert config.model == "deepseek-chat"
