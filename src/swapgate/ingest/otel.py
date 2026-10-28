"""OpenTelemetry GenAI-semconv span ingestor.

Reads span JSON with gen_ai.* attributes, in either flattened
(gen_ai.prompt.0.content) or JSON-blob (gen_ai.request.messages) form.
"""

from __future__ import annotations

import json
from typing import Any

from ..traces import TraceEvent


def _indexed(attrs: dict[str, Any], prefix: str) -> list[Any]:
    items: dict[int, dict[str, Any]] = {}
    for key, value in attrs.items():
        if not key.startswith(prefix):
            continue
        rest = key[len(prefix):].split(".", 1)
        if len(rest) != 2 or not rest[0].isdigit():
            continue
        items.setdefault(int(rest[0]), {})[rest[1]] = value
    return [items[i] for i in sorted(items)]


def _coerce_messages(attrs: dict[str, Any]) -> list[dict[str, str]]:
    blob = attrs.get("gen_ai.request.messages") or attrs.get("gen_ai.prompt.messages")
    if isinstance(blob, str):
        try:
            blob = json.loads(blob)
        except json.JSONDecodeError:
            blob = None
    if isinstance(blob, list):
        out = []
        for msg in blob:
            if isinstance(msg, dict):
                out.append({
                    "role": str(msg.get("role", "user")),
                    "content": str(msg.get("content", "")),
                })
        if out:
            return out
    out = []
    for part in _indexed(attrs, "gen_ai.prompt."):
        out.append({
            "role": str(part.get("role", "user")),
            "content": str(part.get("content", "")),
        })
    return out


def _coerce_output(attrs: dict[str, Any]) -> str:
    blob = attrs.get("gen_ai.response.choices") or attrs.get("gen_ai.completion.choices")
    if isinstance(blob, str):
        try:
            blob = json.loads(blob)
        except json.JSONDecodeError:
            blob = None
    if isinstance(blob, list) and blob:
        first = blob[0] or {}
        if isinstance(first, dict):
            msg = first.get("message", {}) or {}
            if isinstance(msg, dict) and msg.get("content"):
                return str(msg["content"])
            if first.get("content"):
                return str(first["content"])
    parts = _indexed(attrs, "gen_ai.completion.")
    texts = [str(p.get("content", "")) for p in parts if p.get("content")]
    if texts:
        return " ".join(texts)
    direct = attrs.get("gen_ai.response.text") or attrs.get("gen_ai.completion.text")
    return str(direct or "")


def parse_otel_span(span: dict[str, Any]) -> TraceEvent | None:
    """Parse one OTel span dict into a TraceEvent. None if not a GenAI span."""
    attrs = span.get("attributes", {}) or {}
    if not isinstance(attrs, dict):
        return None
    if not any(k.startswith("gen_ai.") for k in attrs):
        return None
    messages = _coerce_messages(attrs)
    if not messages:
        return None
    model = str(
        attrs.get("gen_ai.response.model")
        or attrs.get("gen_ai.request.model")
        or "unknown"
    )
    status = "success"
    span_status = span.get("status", {}) or {}
    if isinstance(span_status, dict) and span_status.get("code") in ("Error", "ERROR", 2):
        status = "failure"
    return TraceEvent(
        trace_id=str(span.get("traceId") or span.get("trace_id") or "otel-unknown"),
        model=model,
        messages=messages,
        output=_coerce_output(attrs),
        timestamp=str(span.get("timestamp") or span.get("startTimeUnixNano") or ""),
        provider=str(attrs.get("gen_ai.system") or "otel"),
        status=status,
        usage={
            k: attrs[k]
            for k in ("gen_ai.usage.input_tokens", "gen_ai.usage.output_tokens")
            if k in attrs
        },
        metadata={"source": "otel", "span": str(span.get("name", ""))},
    )
