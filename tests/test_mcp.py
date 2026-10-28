"""G0: MCP server protocol tests."""

import json

from swapgate.evals import EvalCase, EvalSuite, save_suite
from swapgate.mcp_server import handle_request


def _suite_file(tmp_path) -> str:
    suite = EvalSuite(name="mcp-demo", cases=[
        EvalCase(id="m1",
                 input=[{"role": "user", "content": "Summarise the refund policy"}],
                 rubric=[{"type": "contains", "values": ["refund", "policy"]}],
                 tags=["smoke"]),
    ])
    path = str(tmp_path / "suite.json")
    save_suite(suite, path)
    return path


def test_initialize():
    resp = handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert resp["result"]["serverInfo"]["name"] == "swapgate"
    assert "tools" in resp["result"]["capabilities"]


def test_tools_list_names():
    resp = handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = [t["name"] for t in resp["result"]["tools"]]
    assert names == ["compare_models", "list_evals"]


def test_list_evals(tmp_path):
    resp = handle_request({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                           "params": {"name": "list_evals",
                                      "arguments": {"suite": _suite_file(tmp_path)}}})
    payload = json.loads(resp["result"]["content"][0]["text"])
    assert payload["cases"] == [{"id": "m1", "tags": ["smoke"]}]


def test_compare_models_parity(tmp_path):
    resp = handle_request({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                           "params": {"name": "compare_models",
                                      "arguments": {"suite": _suite_file(tmp_path),
                                                    "baseline": "mock:parity",
                                                    "candidate": "mock:parity"}}})
    payload = json.loads(resp["result"]["content"][0]["text"])
    assert payload["summary"]["passed"] is True
    assert payload["content_hash"]


def test_compare_models_unsigned_shape(tmp_path):
    resp = handle_request({"jsonrpc": "2.0", "id": 7, "method": "tools/call",
                           "params": {"name": "compare_models",
                                      "arguments": {"suite": _suite_file(tmp_path),
                                                    "baseline": "mock:parity",
                                                    "candidate": "mock:parity"}}})
    payload = json.loads(resp["result"]["content"][0]["text"])
    assert payload["content_hash"]
    assert "signature" not in payload and "signature_scheme" not in payload


def test_unknown_tool_and_method():
    resp = handle_request({"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                           "params": {"name": "teleport", "arguments": {}}})
    assert resp["error"]["code"] == -32602
    resp = handle_request({"jsonrpc": "2.0", "id": 6, "method": "nope"})
    assert resp["error"]["code"] == -32601


def test_notifications_get_no_response():
    assert handle_request({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    assert handle_request({"method": "tools/list"}) is None
