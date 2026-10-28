"""Eval runner: async replay of suites against OpenAI-compatible endpoints.

Providers are parsed from a single string:
  mock:parity | mock:regress | mock:seed-N   (deterministic, offline)
  openai-compat:<base-url>|<model>            (live; key from SWAPGATE_API_KEY)

Mock scenarios are fixed scripts so gates are reproducible:
  parity  — answers using the prompt's own key words (passes sane rubrics)
  regress — short refusal (fails content/length rubrics)
  seed-N  — deterministic paraphrase variant N of parity
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol

_WORD_RE = re.compile(r"[A-Za-z]{4,}")


class Provider(Protocol):
    label: str

    async def complete(self, messages: list[dict[str, str]]) -> str:
        ...


def _prompt_text(messages: list[dict[str, str]]) -> str:
    for msg in reversed(messages):
        if msg.get("role") == "user":
            return str(msg.get("content", ""))
    return ""


class MockProvider:
    """Deterministic offline provider for gates, demos and golden tests."""

    def __init__(self, scenario: str = "parity"):
        self.scenario = scenario
        self.label = f"mock:{scenario}"

    async def complete(self, messages: list[dict[str, str]]) -> str:
        prompt = _prompt_text(messages)
        if self.scenario == "regress":
            return "I cannot answer that."
        keywords = _WORD_RE.findall(prompt)[:6]
        about = ", ".join(keywords) if keywords else "your request"
        if self.scenario.startswith("seed-"):
            seed = self.scenario.split("-", 1)[1]
            digest = hashlib.sha256(f"{seed}:{prompt}".encode()).hexdigest()[:8]
            return (
                f"Variant {seed} answer (ref {digest}) regarding {about}. "
                f"In conclusion: the request about {about} is handled."
            )
        return (
            f"Answer regarding {about}. "
            f"In conclusion: the request about {about} is handled."
        )


class OpenAICompatProvider:
    """Live provider for any OpenAI-compatible /chat/completions endpoint."""

    def __init__(self, base_url: str, model: str, api_key: str = "", timeout_s: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key or os.environ.get("SWAPGATE_API_KEY", "")
        self.timeout_s = timeout_s
        self.label = f"openai-compat:{self.base_url}|{self.model}"

    def _post(self, messages: list[dict[str, str]]) -> str:
        body = json.dumps({"model": self.model, "messages": messages}).encode()
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.api_key}"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
            payload = json.loads(resp.read().decode())
        return str(payload["choices"][0]["message"]["content"])

    async def complete(self, messages: list[dict[str, str]]) -> str:
        return await asyncio.to_thread(self._post, messages)


def parse_provider(spec: str) -> Provider:
    if spec.startswith("mock:"):
        return MockProvider(spec[len("mock:"):])
    if spec.startswith("openai-compat:"):
        rest = spec[len("openai-compat:"):]
        base_url, _, model = rest.partition("|")
        if not base_url or not model:
            raise ValueError(f"bad provider spec (want openai-compat:<base-url>|<model>): {spec}")
        return OpenAICompatProvider(base_url, model)
    raise ValueError(f"unknown provider spec: {spec}")


@dataclass
class ReplayResult:
    case_id: str
    output: str


async def replay(
    cases: list[Any],
    provider: Provider,
    concurrency: int = 8,
) -> list[ReplayResult]:
    sem = asyncio.Semaphore(max(1, concurrency))

    async def one(case: Any) -> ReplayResult:
        async with sem:
            return ReplayResult(case_id=case.id, output=await provider.complete(case.input))

    return list(await asyncio.gather(*(one(c) for c in cases)))
