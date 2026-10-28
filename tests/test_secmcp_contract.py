"""P5: sec-MCP v1 contract conformance + emitter tests."""

import json
import os

import pytest

from swapgate.ingest import parse_secmcp
from swapgate.secmcp_emit import emit_event, from_trace, write_log
from swapgate.traces import TraceEvent

ROOT = os.path.join(os.path.dirname(__file__), "..")


def validate(node, schema):
    """Minimal stdlib validator for the schema subset we use."""
    if "const" in schema:
        return node == schema["const"]
    if "enum" in schema:
        return node in schema["enum"]
    if "type" in schema:
        want = schema["type"]
        if want == "number":
            if isinstance(node, bool) or not isinstance(node, (int, float)):
                return False
        elif not isinstance(node, {"object": dict, "string": str,
                                   "array": list, "boolean": bool}[want]):
            return False
    if schema.get("type") == "object" and isinstance(node, dict):
        for key in schema.get("required", []):
            if key not in node:
                return False
        for key, subschema in schema.get("properties", {}).items():
            if key in node and not validate(node[key], subschema):
                return False
    if schema.get("type") == "array" and isinstance(node, list):
        items = schema.get("items")
        if items and not all(validate(v, items) for v in node):
            return False
    return True


@pytest.fixture(scope="module")
def schema():
    with open(os.path.join(ROOT, "schemas", "secmcp-log-v1.json"), encoding="utf-8") as fh:
        return json.load(fh)


def test_fixtures_conform(schema):
    with open(os.path.join(ROOT, "fixtures", "traces-secmcp.jsonl"), encoding="utf-8") as fh:
        rows = [json.loads(line) for line in fh if line.strip()]
    assert validate(rows[0], schema)
    assert validate(rows[1], schema)
    assert not validate(rows[2], schema)  # missing v → invalid by design


def test_invalid_lines_rejected(schema):
    assert not validate({"v": 1}, schema)  # missing tool
    assert not validate({"v": 2, "tool": "x"}, schema)  # wrong version
    assert not validate({"v": 1, "tool": "x",
                         "policy_decision": {"action": "maybe"}}, schema)
    assert not validate({"v": 1, "tool": "x", "latency_ms": "fast"}, schema)
    assert validate({"v": 1, "tool": "x"}, schema)  # minimal valid


def test_emitter_round_trip_and_deny(schema):
    event = TraceEvent(trace_id="t1", model="m",
                       messages=[{"role": "user", "content": "Summarise the refund policy"}],
                       output="done")
    line = from_trace(event, "refund_lookup", args={"order_id": "1"},
                      action="deny", probability=0.97, latency_ms=3)
    assert validate(line, schema)
    assert line["policy_decision"] == {"action": "deny", "probability": 0.97}
    assert line["llm"]["messages"][0]["content"].startswith("Summarise")
    parsed = parse_secmcp(line)
    assert parsed is not None
    assert parsed.tool_calls[0]["policy_decision"]["action"] == "deny"
    with pytest.raises(ValueError):
        emit_event("x", action="maybe")


def test_write_log_jsonl(tmp_path, schema):
    path = str(tmp_path / "sec.jsonl")
    write_log(path, [emit_event("a"), emit_event("b", action="deny")])
    with open(path, encoding="utf-8") as fh:
        rows = [json.loads(line) for line in fh]
    assert len(rows) == 2
    assert all(validate(r, schema) for r in rows)
