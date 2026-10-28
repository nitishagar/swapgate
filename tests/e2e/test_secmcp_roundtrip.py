"""E2E: emitter -> capture --from secmcp -> build/approve -> compare -> verify."""

import json
import subprocess
import sys

from swapgate.secmcp_emit import from_trace, write_log
from swapgate.traces import TraceEvent

CLI = [sys.executable, "-m", "swapgate.cli"]

PROMPTS = [
    "Summarise the refund policy for delayed flights",
    "What is the refund policy for cancelled flights?",
    "Explain baggage allowance rules clearly",
]


def _run(argv: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(CLI + argv, capture_output=True, text=True, check=False)


def test_secmcp_roundtrip(tmp_path):
    events = [TraceEvent(trace_id=f"e{i}", model="sarvam-30b",
                         messages=[{"role": "user", "content": p}],
                         output=f"Mock answer {i}")
              for i, p in enumerate(PROMPTS)]
    lines = [from_trace(e, "support_answer", action="allow", probability=0.99 - i * 0.01)
             for i, e in enumerate(events)]
    lines.append(from_trace(events[0], "db_delete", args={"table": "users"},
                            action="deny", probability=0.97))
    log = str(tmp_path / "sec.jsonl")
    write_log(log, lines)

    captured = str(tmp_path / "events.jsonl")
    proc = _run(["capture", "--from", "secmcp", "--in", log, "--out", captured])
    assert proc.returncode == 0, proc.stderr
    assert "captured 4 events" in proc.stdout
    with open(captured, encoding="utf-8") as fh:
        rows = [json.loads(line) for line in fh]
    assert any(c.get("policy_decision", {}).get("action") == "deny"
               for r in rows for c in r["tool_calls"])

    suite = str(tmp_path / "suite.json")
    assert _run(["build-evals", "--in", captured, "--out", suite,
                 "--name", "sec"]).returncode == 0
    assert _run(["build-evals", "--out", suite, "--approve"]).returncode == 0

    receipt = str(tmp_path / "receipt.json")
    key = str(tmp_path / "key")
    proc = _run(["compare", "--suite", suite, "--baseline", "mock:parity",
                 "--candidate", "mock:parity", "--fail-under", "0.0",
                 "--out", receipt, "--key", key])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    proc = _run(["verify", "--receipt", receipt, "--key", key])
    assert proc.returncode == 0, proc.stdout
    assert "receipt VALID" in proc.stdout
