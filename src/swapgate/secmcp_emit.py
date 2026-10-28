"""Reference sec-MCP v1 log emitter (integration aid + e2e producer).

Produces lines conforming to schemas/secmcp-log-v1.json. The primary input is
a TraceEvent, wrapped with the tool-call envelope; `emit_event` covers fully
synthetic lines.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from .traces import TraceEvent


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def emit_event(tool: str, args: dict[str, Any] | None = None,
               action: str = "allow", probability: float = 1.0,
               latency_ms: float = 0.0, session: str = "",
               result: str = "",
               llm: dict[str, Any] | None = None,
               event_id: str | None = None, ts: str | None = None) -> dict[str, Any]:
    if action not in ("allow", "deny"):
        raise ValueError(f"policy action must be allow|deny, got {action!r}")
    return {
        "v": 1,
        "id": event_id or str(uuid.uuid4()),
        "ts": ts or _now(),
        "session": session,
        "tool": tool,
        "args": args or {},
        "result": result,
        "latency_ms": latency_ms,
        "policy_decision": {"action": action, "probability": probability},
        **({"llm": llm} if llm is not None else {}),
    }


def from_trace(event: TraceEvent, tool: str, args: dict[str, Any] | None = None,
               action: str = "allow", probability: float = 1.0,
               latency_ms: float = 0.0, session: str = "") -> dict[str, Any]:
    """Wrap a TraceEvent as a v1 log line with an LLM block."""
    return emit_event(
        tool, args=args, action=action, probability=probability,
        latency_ms=latency_ms, session=session or event.trace_id,
        llm={"model": event.model,
             "messages": [dict(m) for m in event.messages],
             "output": event.output},
        event_id=f"{event.trace_id}:{tool}",
    )


def write_log(path: str, events: list[dict[str, Any]]) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        for event in events:
            fh.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
