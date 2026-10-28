"""LiteLLM ingestor.

Accepts two shapes:
1. LiteLLM StandardLoggingPayload-style dicts (model, messages, response,
   response_obj/choices, usage, status fields).
2. The minimal shape {messages, response, model}.
"""

from __future__ import annotations

import json
from typing import Any

from ..traces import TraceEvent


def _coerce_messages(raw: Any) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    if not isinstance(raw, list):
        return out
    for msg in raw:
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role", "user"))
        content = msg.get("content", "")
        if isinstance(content, list):  # content parts
            content = " ".join(
                str(p.get("text", p)) if isinstance(p, dict) else str(p)
                for p in content
            )
        out.append({"role": role, "content": str(content)})
    return out


def _coerce_output(response: Any) -> str:
    if response is None:
        return ""
    if isinstance(response, str):
        return response
    if isinstance(response, dict):
        choices = response.get("choices", [])
        if choices and isinstance(choices, list):
            first = choices[0] or {}
            msg = first.get("message", {}) or {}
            if isinstance(msg, dict) and msg.get("content"):
                return str(msg["content"])
            if first.get("text"):
                return str(first["text"])
        if response.get("content"):
            return str(response["content"])
        return json.dumps(response, ensure_ascii=False, sort_keys=True)
    return str(response)


def parse_litellm(payload: dict[str, Any]) -> TraceEvent | None:
    """Parse one LiteLLM logging payload into a TraceEvent. None if unusable."""
    messages = _coerce_messages(payload.get("messages"))
    if not messages:
        return None
    response = payload.get("response", payload.get("response_obj"))
    status = "success"
    status_fields = payload.get("status_fields", {}) or {}
    if isinstance(status_fields, dict) and status_fields.get("llm_api_status") == "failure":
        status = "failure"
    if payload.get("error_information"):
        status = "failure"
    model = str(payload.get("model") or payload.get("requested_model") or "unknown")
    return TraceEvent(
        trace_id=str(payload.get("id") or payload.get("trace_id") or "litellm-unknown"),
        model=model,
        messages=messages,
        output=_coerce_output(response),
        timestamp=str(payload.get("start_time") or payload.get("timestamp") or ""),
        provider=str(payload.get("custom_llm_provider") or payload.get("provider") or "litellm"),
        status=status,
        usage=dict(payload.get("usage") or {}),
        metadata={"source": "litellm"},
    )
