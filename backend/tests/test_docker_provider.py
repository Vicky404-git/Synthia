"""Docker adapter tests using mocks (no real daemon calls)."""

from __future__ import annotations

import pytest

from app.config import Settings
from app.errors import ProviderError
from app.providers.docker_provider import DockerProvider


class _FakeImage:
    tags = ["nginx:latest"]
    short_id = "abc"


class _FakeContainer:
    short_id = "abc123def456"
    name = "web"
    status = "running"
    image = _FakeImage()

    def __init__(self, cid="abc123def456"):
        self.id = cid
        self.attrs = {
            "Id": cid,
            "Name": "/web",
            "Config": {"Image": "nginx:latest", "Env": ["PATH=/usr/bin", "PORT=80"]},
            "State": {"Status": "running", "StartedAt": "2024-01-01T00:00:00Z"},
            "RestartCount": 2,
        }

    def logs(self, tail=50, timestamps=False):
        return "\n".join(f"line {i}" for i in range(tail)).encode()


class _FakeContainers:
    def list(self, all=False):
        return [_FakeContainer()]

    def get(self, container_id):
        return _FakeContainer(container_id)


class _FakeClient:
    containers = _FakeContainers()

    def ping(self):
        return True


@pytest.fixture
def provider():
    settings = Settings(docker_enabled=True, app_env="test")
    instance = DockerProvider(settings)
    instance._client = lambda: _FakeClient()  # type: ignore[assignment]
    return instance


def test_list_containers(provider):
    result = provider.list_containers()
    assert result.data["count"] == 1
    assert result.data["containers"][0]["name"] == "web"
    assert result.data["containers"][0]["state"] == "running"


def test_inspect_container(provider):
    result = provider.inspect_container("abc123def456")
    assert result.data["name"] == "web"
    assert "PORT" in result.data["env_keys"]


def test_container_logs_are_bounded(provider):
    result = provider.container_logs("abc123def456", tail=150)
    assert result.data["tail"] == 150
    assert len(result.data["lines"]) == 150


def test_disabled_docker_is_reported():
    provider = DockerProvider(Settings(docker_enabled=False))
    assert provider.health().status.value == "disabled"
    with pytest.raises(Exception):
        provider.list_containers()


def test_docker_disabled_in_production():
    provider = DockerProvider(Settings(docker_enabled=True, app_env="production"))
    health = provider.health()
    assert health.status.value == "disabled"
    assert "production" in health.detail.lower()


def test_docker_error_is_mapped():
    provider = DockerProvider(Settings(docker_enabled=True, app_env="test"))

    class _Boom:
        @property
        def containers(self):
            class _C:
                def list(self, all=False):
                    raise RuntimeError("daemon down")

            return _C()

    provider._client = lambda: _Boom()  # type: ignore[assignment]
    with pytest.raises(ProviderError):
        provider.list_containers()
