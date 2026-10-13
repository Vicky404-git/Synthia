"""Cloud provider adapters.

Each adapter is independent and reports its own configuration status honestly.
Adding a provider means adding a module here plus registering its tools; no
changes to the assistant core are required.
"""

from __future__ import annotations

from .aws_provider import AWSProvider
from .azure_provider import AzureProvider
from .base import CloudProvider, ProviderHealth
from .demo_provider import DemoProvider
from .docker_provider import DockerProvider
from .registry import ProviderRegistry, get_provider_registry

__all__ = [
    "AWSProvider",
    "AzureProvider",
    "CloudProvider",
    "DemoProvider",
    "DockerProvider",
    "ProviderHealth",
    "ProviderRegistry",
    "get_provider_registry",
]
