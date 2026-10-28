"""E2E: local LiteLLM (mock) -> capture -> build-evals -> compare -> verify.

Hermetic: no keys, no network (mock completions), telemetry asserted off.
"""

import json
import os
import subprocess
import sys

import pytest

litellm = pytest.importorskip("litellm")

from litellm_harness import run_local_traces, write_rows  # noqa: E402

CLI = [sys.executable, "-m", "swapgate.cli"]


def _run(argv: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(CLI + argv, capture_output=True, text=True, check=False)


def test_local_tracing_pipeline(tmp_path):
    traces = str(tmp_path / "traces.jsonl")
    write_rows(run_local_traces(), traces)

    events = str(tmp_path / "events.jsonl")
    proc = _run(["capture", "--from", "litellm", "--in", traces, "--out", events])
    assert proc.returncode == 0, proc.stderr
    assert "captured 5 events" in proc.stdout

    with open(events, encoding="utf-8") as fh:
        rows = [json.loads(line) for line in fh]
    failures = [r for r in rows if r.get("status") == "failure"]
    assert len(failures) == 1

    suite = str(tmp_path / "suite.json")
    proc = _run(["build-evals", "--in", events, "--out", suite, "--name", "e2e"])
    assert proc.returncode == 0, proc.stderr
    assert os.path.exists(str(tmp_path / "suite.pending.json"))
    proc = _run(["build-evals", "--out", suite, "--approve"])
    assert proc.returncode == 0, proc.stderr

    receipt = str(tmp_path / "receipt.json")
    key = str(tmp_path / "key")
    proc = _run(["compare", "--suite", suite, "--baseline", "mock:parity",
                 "--candidate", "mock:seed-3", "--fail-under", "0.0",
                 "--max-regression", "0.5", "--out", receipt, "--key", key])
    assert proc.returncode == 0, proc.stdout + proc.stderr

    proc = _run(["verify", "--receipt", receipt, "--key", key])
    assert proc.returncode == 0, proc.stdout
    assert "receipt VALID" in proc.stdout
    assert litellm.telemetry is False
