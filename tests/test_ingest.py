"""G0: ingestor unit tests over checked-in fixtures."""

import os

from conftest import FIXTURES
from swapgate.ingest import parse_litellm, parse_otel_span, parse_secmcp
from swapgate.traces import read_jsonl


def test_litellm_standard_payload():
    rows = read_jsonl(os.path.join(FIXTURES, "traces-litellm.jsonl"))
    assert len(rows) == 4  # corrupt line skipped
    ev = parse_litellm(rows[0])
    assert ev is not None
    assert ev.trace_id == "lit-001"
    assert ev.model == "gpt-4o-mini"
    assert ev.messages[0]["role"] == "user"
    assert "refund policy" in ev.messages[0]["content"]
    assert "7 days" in ev.output
    assert ev.status == "success"
    assert ev.usage["prompt_tokens"] == 12


def test_litellm_minimal_shape():
    rows = read_jsonl(os.path.join(FIXTURES, "traces-litellm.jsonl"))
    ev = parse_litellm(rows[2])
    assert ev is not None
    assert ev.model == "claude-sonnet-4"
    assert "GST notice" in ev.messages[0]["content"]


def test_litellm_failure_status():
    rows = read_jsonl(os.path.join(FIXTURES, "traces-litellm.jsonl"))
    ev = parse_litellm(rows[3])
    assert ev is not None
    assert ev.status == "failure"


def test_litellm_rejects_empty():
    assert parse_litellm({}) is None
    assert parse_litellm({"messages": []}) is None


def test_otel_flattened_span():
    rows = read_jsonl(os.path.join(FIXTURES, "traces-otel.jsonl"))
    ev = parse_otel_span(rows[0])
    assert ev is not None
    assert ev.trace_id == "otel-001"
    assert "baggage allowance" in ev.messages[0]["content"]
    assert "23kg" in ev.output
    assert ev.provider == "openai"


def test_otel_blob_span():
    rows = read_jsonl(os.path.join(FIXTURES, "traces-otel.jsonl"))
    ev = parse_otel_span(rows[1])
    assert ev is not None
    assert "Aadhaar" in ev.messages[0]["content"]
    assert "cannot validate" in ev.output


def test_otel_rejects_non_genai():
    rows = read_jsonl(os.path.join(FIXTURES, "traces-otel.jsonl"))
    assert parse_otel_span(rows[2]) is None


def test_secmcp_with_llm_block():
    rows = read_jsonl(os.path.join(FIXTURES, "traces-secmcp.jsonl"))
    ev = parse_secmcp(rows[0])
    assert ev is not None
    assert ev.model == "sarvam-30b"
    assert ev.tool_calls[0]["tool"] == "refund_lookup"
    assert ev.tool_calls[0]["policy_decision"]["action"] == "allow"
    assert "ORD-42" in ev.messages[-1]["content"]


def test_secmcp_tool_only_record():
    rows = read_jsonl(os.path.join(FIXTURES, "traces-secmcp.jsonl"))
    ev = parse_secmcp(rows[1])
    assert ev is not None
    assert "db_delete" in ev.messages[0]["content"]
    assert ev.tool_calls[0]["policy_decision"]["action"] == "deny"


def test_secmcp_rejects_wrong_version():
    rows = read_jsonl(os.path.join(FIXTURES, "traces-secmcp.jsonl"))
    assert parse_secmcp(rows[2]) is None
