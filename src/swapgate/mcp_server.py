"""Minimal stdio MCP server (JSON-RPC 2.0, no dependencies).

Tools:
  compare_models — run baseline-vs-candidate over a suite file, return the receipt summary
  list_evals     — list case ids + tags of a suite file
"""

from __future__ import annotations

import json
import sys
from typing import Any

from .compare import compare
from .evals import load_suite
from .judges.deterministic import DeterministicJudge
from .judges.typed import TypedJudge
from .receipt import build_receipt_body, content_hash

SERVER_NAME = "swapgate"
SERVER_VERSION = "0.1.0"


def _judge(name: str) -> Any:
    if name == "deterministic":
        return DeterministicJudge()
    if name == "typed":
        return TypedJudge()
    raise ValueError(f"unknown judge for MCP: {name} (want deterministic|typed)")


def tool_compare_models(args: dict[str, Any], suite_dir: str = "") -> dict[str, Any]:
    from .runner import parse_provider

    suite = load_suite(args["suite"])
    result = compare(
        suite,
        parse_provider(args.get("baseline", "mock:parity")),
        parse_provider(args.get("candidate", "mock:parity")),
        _judge(args.get("judge", "deterministic")),
        fail_under=float(args.get("fail_under", 0.0)),
        max_regression=float(args.get("max_regression", 1.0)),
    )
    body = build_receipt_body(result.summary(), [c.to_dict() for c in result.cases])
    body["content_hash"] = content_hash(body)
    return body


def tool_list_evals(args: dict[str, Any]) -> dict[str, Any]:
    suite = load_suite(args["suite"])
    return {
        "name": suite.name,
        "version": suite.version,
        "cases": [{"id": c.id, "tags": c.tags} for c in suite.cases],
    }


TOOLS = {
    "compare_models": {
        "description": "Replay an eval suite on baseline and candidate models; return the swap receipt.",
        "inputSchema": {
            "type": "object",
            "required": ["suite"],
            "properties": {
                "suite": {"type": "string", "description": "Path to suite JSON"},
                "baseline": {"type": "string", "default": "mock:parity"},
                "candidate": {"type": "string", "default": "mock:parity"},
                "judge": {"type": "string", "default": "deterministic"},
                "fail_under": {"type": "number", "default": 0.0},
                "max_regression": {"type": "number", "default": 1.0},
            },
        },
        "handler": tool_compare_models,
    },
    "list_evals": {
        "description": "List eval case ids and tags of a suite file.",
        "inputSchema": {
            "type": "object",
            "required": ["suite"],
            "properties": {"suite": {"type": "string"}},
        },
        "handler": tool_list_evals,
    },
}


def handle_request(request: dict[str, Any]) -> dict[str, Any] | None:
    if request.get("jsonrpc") != "2.0":
        return None
    msg_id = request.get("id")
    method = request.get("method", "")

    def ok(result: Any) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}

    def err(code: int, message: str) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}

    if method == "initialize":
        return ok({"protocolVersion": "2024-11-05",
                   "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                   "capabilities": {"tools": {}}})
    if method in ("notifications/initialized",):
        return None
    if method == "tools/list":
        return ok({"tools": [
            {"name": name, "description": spec["description"], "inputSchema": spec["inputSchema"]}
            for name, spec in TOOLS.items()
        ]})
    if method == "tools/call":
        params = request.get("params", {}) or {}
        tool = TOOLS.get(params.get("name", ""))
        if tool is None:
            return err(-32602, f"unknown tool: {params.get('name')}")
        try:
            result = tool["handler"](params.get("arguments", {}) or {})
        except Exception as exc:  # surface tool errors as JSON-RPC errors
            return err(-32000, f"{params.get('name')} failed: {exc}")
        return ok({"content": [{"type": "text", "text": json.dumps(result, sort_keys=True)}]})
    if msg_id is None:
        return None
    return err(-32601, f"unknown method: {method}")


def serve() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue
        response = handle_request(request)
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()
