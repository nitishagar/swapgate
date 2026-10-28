"""E2E: --rubrics llm path through the real CLI (recorded fixtures, offline)."""

import json
import os
import subprocess
import sys

from swapgate.cluster import cluster_events
from swapgate.rubrics_llm import render_rubric_prompt
from swapgate.traces import TraceEvent, read_jsonl

CLI = [sys.executable, "-m", "swapgate.cli"]
FIXTURES = os.path.join(os.path.dirname(__file__), "..", "..", "fixtures")


def _run(argv: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(CLI + argv, capture_output=True, text=True, check=False)


def _fixtures_for(events_path: str, fixtures_path: str) -> None:
    events = [TraceEvent.from_dict(r) for r in read_jsonl(events_path)]
    mapping = {}
    for cluster in cluster_events(events, 8):
        prompt = render_rubric_prompt(cluster.template, cluster.exemplar)
        mapping[prompt] = ('[{"type": "contains", "values": ["refund", "policy"]},'
                           ' {"type": "min_length", "value": 10}]')
    with open(fixtures_path, "w", encoding="utf-8") as fh:
        json.dump(mapping, fh)


def test_rubrics_llm_end_to_end(tmp_path):
    events = str(tmp_path / "events.jsonl")
    proc = _run(["capture", "--from", "litellm",
                 "--in", os.path.join(FIXTURES, "traces-litellm.jsonl"),
                 "--out", events])
    assert proc.returncode == 0, proc.stderr

    fixtures = str(tmp_path / "rubrics.json")
    _fixtures_for(events, fixtures)

    suite = str(tmp_path / "suite.json")
    proc = _run(["build-evals", "--in", events, "--out", suite, "--name", "llm",
                 "--rubrics", "llm", "--rubrics-fixtures", fixtures])
    assert proc.returncode == 0, proc.stderr
    proc = _run(["build-evals", "--out", suite, "--approve"])
    assert proc.returncode == 0, proc.stderr
    with open(suite, encoding="utf-8") as fh:
        cases = json.load(fh)["cases"]
    assert cases
    assert any(c["type"] == "contains" for c in cases[0]["rubric"])

    receipt = str(tmp_path / "receipt.json")
    proc = _run(["compare", "--suite", suite, "--baseline", "mock:parity",
                 "--candidate", "mock:parity", "--out", receipt])
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_rubrics_llm_needs_fixtures_or_env(tmp_path, monkeypatch):
    events = str(tmp_path / "events.jsonl")
    proc = _run(["capture", "--from", "litellm",
                 "--in", os.path.join(FIXTURES, "traces-litellm.jsonl"),
                 "--out", events])
    assert proc.returncode == 0, proc.stderr
    monkeypatch.delenv("SWAPGATE_BASE_URL", raising=False)
    monkeypatch.delenv("SWAPGATE_MODEL", raising=False)
    env = {k: v for k, v in os.environ.items()
           if k not in ("SWAPGATE_BASE_URL", "SWAPGATE_MODEL")}
    proc = subprocess.run(CLI + ["build-evals", "--in", events,
                                 "--out", str(tmp_path / "s.json"),
                                 "--rubrics", "llm"],
                          capture_output=True, text=True, env=env, check=False)
    assert proc.returncode == 1
    assert "--rubrics-fixtures" in proc.stderr
