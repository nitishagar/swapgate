"""sec-MCP tool-call log ingestor.

Schema defined here (v1) — there is no upstream sec-MCP log format yet, so
SwapGate specifies the contract it consumes:

    {"v": 1, "ts": "...", "session": "...", "tool": "name",
     "args": {...}, "policy_decision": {"action": "allow"|"deny",
     "probability": 0.0-1.0}, "latency_ms": 12,
     "llm": {"model": "...", "messages": [...], "output": "..."}}

The `llm` block is optional; without it the tool call itself becomes the
eval input (tool + args rendered as the user turn).
"""

from __future__ import annotations

import json
from typing import Any

from ..traces import TraceEvent

SCHEMA_VERSION = 1


def parse_secmcp(record: dict[str, Any]) -> TraceEvent | None:
    """Parse one sec-MCP tool-call log record. None if not v1-shaped."""
    if record.get("v") != SCHEMA_VERSION or "tool" not in record:
        return None
    llm = record.get("llm") or {}
    messages: list[dict[str, str]] = []
    output = ""
    model = "unknown"
    if isinstance(llm, dict) and llm.get("messages"):
        for msg in llm["messages"]:
            if isinstance(msg, dict):
                messages.append({
                    "role": str(msg.get("role", "user")),
                    "content": str(msg.get("content", "")),
                })
        output = str(llm.get("output", ""))
        model = str(llm.get("model", "unknown"))
    else:
        args = record.get("args", {})
        messages = [{
            "role": "user",
            "content": (
                f"Tool call: {record.get('tool')}\n"
                f"Arguments: {json.dumps(args, ensure_ascii=False, sort_keys=True)}"
            ),
        }]
        output = str(record.get("result", ""))
    decision = record.get("policy_decision") or {}
    return TraceEvent(
        trace_id=str(record.get("id") or record.get("session") or "secmcp-unknown"),
        model=model,
        messages=messages,
        output=output,
        timestamp=str(record.get("ts", "")),
        provider="sec-mcp",
        status="success",
        tool_calls=[{
            "tool": str(record.get("tool")),
            "args": record.get("args", {}),
            "policy_decision": decision,
            "latency_ms": record.get("latency_ms"),
        }],
        metadata={"source": "sec-mcp", "session": str(record.get("session", ""))},
    )
