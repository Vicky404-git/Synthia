"""Offline demo LLM provider.

This provider never calls a network service. It exists so the application is
fully usable (conversation UI, tool routing, history) without any paid
credentials. Answers are clearly labelled as demo content.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from ..config import Settings
from .base import LLMProvider, LLMResult

_DEMO_KNOWLEDGE: dict[str, str] = {
    "ec2 vs container": (
        "An EC2 instance is a full virtual machine with its own kernel, while a "
        "container shares the host kernel and packages only the application and "
        "its dependencies. EC2 gives stronger isolation and more control; "
        "containers start faster and are lighter to run."
    ),
    "what is ec2": (
        "EC2 (Elastic Compute Cloud) provides resizable virtual servers in AWS. "
        "You choose an instance type, launch it into a VPC, and pay for the "
        "compute time you use."
    ),
    "what is s3": (
        "S3 (Simple Storage Service) is AWS object storage. Data lives in "
        "buckets as objects addressed by key, with configurable durability, "
        "versioning, and access policies."
    ),
    "what is docker": (
        "Docker packages an application and its dependencies into an image. "
        "Running an image produces a container, an isolated process on the host."
    ),
    "what is cloud computing": (
        "Cloud computing is the on-demand delivery of compute, storage, and "
        "networking as metered services over the internet, backed by provider "
        "data centres and APIs."
    ),
}


class DemoLLMProvider(LLMProvider):
    id = "demo"
    supports_structured = False

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def model(self) -> str:
        return "synthia-demo"

    def _answer(self, messages: list[dict[str, str]]) -> str:
        user = ""
        for message in reversed(messages):
            if message.get("role") == "user":
                user = message.get("content", "")
                break
        lowered = user.lower()
        if "ec2" in lowered and "container" in lowered:
            return f"[demo knowledge base] {_DEMO_KNOWLEDGE['ec2 vs container']}"
        for key, value in _DEMO_KNOWLEDGE.items():
            if key in lowered:
                return f"[demo knowledge base] {value}"
        return (
            "[demo mode] I am running without a live LLM because no API key is "
            "configured. I can still run read-only cloud tools, show provider "
            "status, and record transcription history. Set LLM_PROVIDER=openai "
            "and LLM_API_KEY to enable real general-purpose answers.\n\n"
            f"You asked: {user!r}"
        )

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int | None = None,
        temperature: float = 0.2,
    ) -> LLMResult:
        return LLMResult(
            text=self._answer(messages),
            provider=self.id,
            model=self.model,
            usage={"demo": True},
        )

    async def stream(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int | None = None,
        temperature: float = 0.2,
    ) -> AsyncIterator[str]:
        text = self._answer(messages)
        for token in text.split(" "):
            yield token + " "
            await asyncio.sleep(0.01)
