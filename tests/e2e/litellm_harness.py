"""Shared helpers for the local-tracing e2e: drive in-process LiteLLM (mock).

Everything runs offline: `mock_response` short-circuits completions (no network,
no keys) and telemetry is forced off. Failures come from an Exception instance
as `mock_response`, which raises through `completion()` and fires the failure
hook. Importable by scripts (e.g. the P6 report generator) as well as pytest.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import litellm

PROMPTS = [
    "Summarise the refund policy for delayed flights",
    "What is the refund policy for cancelled flights?",
    "Explain baggage allowance rules clearly",
    "Draft a GST notice reply for notice 9912",
]

FAILURE_SENTINEL = "e2e injected failure"


def _response_text(response_obj: Any) -> str:
    try:
        choices = getattr(response_obj, "choices", None) or []
        if choices:
            return str(choices[0].message.content or "")
    except (AttributeError, IndexError, TypeError):
        pass
    return "" if response_obj is None else str(response_obj)


class _Capture(litellm.CustomLogger):
    """Record hook args as minimal-shape SwapGate rows."""

    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []
        self._failed_kwargs: list[dict[str, Any]] = []

    def log_success_event(self, kwargs, response_obj, start_time, end_time):  # noqa: ANN001,ANN202
        messages = kwargs.get("messages", [])
        self.rows.append({
            "id": str(uuid.uuid4()),
            "model": str(kwargs.get("model", "unknown")),
            "messages": messages if isinstance(messages, list) else [],
            "response": _response_text(response_obj),
            "custom_llm_provider": str(kwargs.get("custom_llm_provider", "openai")),
            "status_fields": {"llm_api_status": "success"},
        })

    def log_failure_event(self, kwargs, response_obj, start_time, end_time):  # noqa: ANN001,ANN202
        self._failed_kwargs.append(dict(kwargs))


def run_local_traces(prompts: list[str] | None = None) -> list[dict[str, Any]]:
    """Run mock completions locally; return minimal-shape trace rows."""
    litellm.telemetry = False
    assert litellm.telemetry is False, "hermeticity requires telemetry off"
    capture = _Capture()
    previous = list(litellm.callbacks or [])
    litellm.callbacks = [*previous, capture]
    try:
        for prompt in prompts or PROMPTS:
            litellm.completion(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                mock_response=f"Mock answer regarding {prompt[:60]}.",
            )
        try:
            litellm.completion(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": "Trigger the failure hook"}],
                mock_response=ValueError(FAILURE_SENTINEL),
            )
        except Exception as exc:  # noqa: BLE001 — the failure path is the point
            for kwargs in capture._failed_kwargs:
                messages = kwargs.get("messages", [])
                capture.rows.append({
                    "id": str(uuid.uuid4()),
                    "model": str(kwargs.get("model", "unknown")),
                    "messages": messages if isinstance(messages, list) else [],
                    "response": "",
                    "error_information": {
                        "error_code": type(exc).__name__,
                        "error_message": str(exc)[:200],
                    },
                    "status_fields": {"llm_api_status": "failure"},
                })
    finally:
        litellm.callbacks = previous
    return capture.rows


def write_rows(rows: list[dict[str, Any]], path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
