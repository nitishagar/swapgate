"""G1: CLI end-to-end tests (capture -> build-evals -> compare -> report -> verify)."""

import json
import os

from conftest import FIXTURES
from swapgate.cli import EXIT_GATE_FAIL, EXIT_OK, main
from swapgate.evals import load_suite


def _capture(tmp_path, source="litellm", redact=""):
    out = str(tmp_path / "events.jsonl")
    argv = ["capture", "--from", source,
            "--in", os.path.join(FIXTURES, f"traces-{source}.jsonl"),
            "--out", out]
    if redact:
        argv += ["--redact", redact]
    assert main(argv) == EXIT_OK
    with open(out, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh]


def test_capture_litellm_counts(tmp_path, capsys):
    events = _capture(tmp_path)
    assert len(events) == 4
    assert "skipped 1" in capsys.readouterr().out


def test_capture_redacts_pii(tmp_path):
    events = _capture(tmp_path, redact="india")
    blob = json.dumps(events)
    assert "priya@example.com" not in blob
    assert "ABCDE1234F" not in blob
    assert "<EMAIL_" in blob and "<PAN_" in blob


def test_capture_all_sources_parse(tmp_path):
    assert len(_capture(tmp_path, "otel")) == 2
    assert len(_capture(tmp_path, "secmcp")) == 2


def test_build_evals_pending_then_approve(tmp_path):
    _capture(tmp_path)
    suite_path = str(tmp_path / "suite.json")
    assert main(["build-evals", "--in", str(tmp_path / "events.jsonl"),
                 "--out", suite_path, "--name", "cli"]) == EXIT_OK
    assert os.path.exists(str(tmp_path / "suite.pending.json"))
    assert not os.path.exists(suite_path)
    assert main(["build-evals", "--in", str(tmp_path / "events.jsonl"),
                 "--out", suite_path, "--approve"]) == EXIT_OK
    assert load_suite(suite_path).name == "cli"


def test_build_evals_approve_without_pending_fails(tmp_path):
    assert main(["build-evals", "--in", os.path.join(FIXTURES, "traces-litellm.jsonl"),
                 "--out", str(tmp_path / "s.json"), "--approve"]) != EXIT_OK


def _suite_for_compare(tmp_path) -> str:
    _capture(tmp_path)
    suite_path = str(tmp_path / "suite.json")
    main(["build-evals", "--in", str(tmp_path / "events.jsonl"),
          "--out", suite_path, "--name", "cmp"])
    main(["build-evals", "--in", str(tmp_path / "events.jsonl"),
          "--out", suite_path, "--approve"])
    return suite_path


def test_compare_parity_passes(tmp_path):
    suite = _suite_for_compare(tmp_path)
    receipt = str(tmp_path / "receipt.json")
    assert main(["compare", "--suite", suite, "--baseline", "mock:parity",
                 "--candidate", "mock:parity", "--out", receipt]) == EXIT_OK
    assert os.path.exists(receipt)


def test_compare_regress_fails_gate(tmp_path):
    suite = _suite_for_compare(tmp_path)
    code = main(["compare", "--suite", suite, "--baseline", "mock:parity",
                 "--candidate", "mock:regress", "--fail-under", "0.5"])
    assert code == EXIT_GATE_FAIL


def test_compare_writes_signed_receipt_and_report(tmp_path):
    suite = _suite_for_compare(tmp_path)
    receipt = str(tmp_path / "r.json")
    report = str(tmp_path / "r.md")
    key = str(tmp_path / "k")
    code = main(["compare", "--suite", suite, "--baseline", "mock:parity",
                 "--candidate", "mock:parity", "--out", receipt, "--report", report,
                 "--key", key])
    assert code == EXIT_OK
    with open(receipt, encoding="utf-8") as fh:
        assert json.load(fh)["signature_scheme"] == "hmac-sha256-v1"
    assert os.path.exists(report)
    assert main(["verify", "--receipt", receipt, "--key", key]) == EXIT_OK


def test_verify_rejects_tampered(tmp_path):
    suite = _suite_for_compare(tmp_path)
    receipt = str(tmp_path / "r.json")
    key = str(tmp_path / "k")
    main(["compare", "--suite", suite, "--baseline", "mock:parity",
          "--candidate", "mock:parity", "--out", receipt, "--key", key])
    with open(receipt, encoding="utf-8") as fh:
        data = json.load(fh)
    data["summary"]["passed"] = False
    with open(receipt, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    assert main(["verify", "--receipt", receipt, "--key", key]) == EXIT_GATE_FAIL


def test_report_renders_both_formats(tmp_path):
    suite = _suite_for_compare(tmp_path)
    receipt = str(tmp_path / "r.json")
    main(["compare", "--suite", suite, "--baseline", "mock:parity",
          "--candidate", "mock:parity", "--out", receipt])
    md = str(tmp_path / "r.md")
    html_path = str(tmp_path / "r.html")
    assert main(["report", "--receipt", receipt, "--format", "md", "--out", md]) == EXIT_OK
    assert main(["report", "--receipt", receipt, "--format", "html", "--out", html_path]) == EXIT_OK
    with open(md, encoding="utf-8") as fh:
        assert "Swap receipt" in fh.read()
    with open(html_path, encoding="utf-8") as fh:
        assert "<html" in fh.read()


def test_report_renders_fence_breaking_receipt(tmp_path):
    from swapgate.receipt import build_receipt_body

    body = build_receipt_body(
        {"suite": "f", "suite_version": "0.1.0", "n_cases": 1, "judge": "d",
         "baseline": "b", "candidate": "c", "baseline_pass_rate": 1.0,
         "candidate_pass_rate": 0.0, "regression_gap": 1.0, "fail_under": 0.0,
         "max_regression": 1.0, "passed": False, "regressed_case_ids": ["c1"]},
        [{"case_id": "c1", "baseline_output": "ok",
          "baseline_verdict": {"passed": True, "label": "pass"},
          "candidate_output": "x ``` y", "candidate_verdict": {"passed": False, "label": "fail"},
          "regressed": True}],
    )
    receipt = str(tmp_path / "r.json")
    with open(receipt, "w", encoding="utf-8") as fh:
        json.dump(body, fh)
    out = str(tmp_path / "r.md")
    assert main(["report", "--receipt", receipt, "--format", "md", "--out", out]) == EXIT_OK
    with open(out, encoding="utf-8") as fh:
        text = fh.read()
    assert text.count("```") == 4
    assert "´´´" in text


def test_parser_exception_aborts_run_without_output(tmp_path):
    import subprocess
    import sys

    bad = str(tmp_path / "bad.jsonl")
    with open(bad, "w", encoding="utf-8") as fh:
        fh.write('{"messages": [{"role": "user", "content": "hi"}], "usage": 5}\n')
    out = str(tmp_path / "o.jsonl")
    proc = subprocess.run([sys.executable, "-m", "swapgate.cli", "capture",
                           "--from", "litellm", "--in", bad, "--out", out],
                          capture_output=True, text=True, check=False)
    assert proc.returncode != 0
    assert not os.path.exists(out)


def test_compare_unsigned_shape(tmp_path):
    suite = _suite_for_compare(tmp_path)
    receipt = str(tmp_path / "u.json")
    assert main(["compare", "--suite", suite, "--baseline", "mock:parity",
                 "--candidate", "mock:parity", "--out", receipt]) == EXIT_OK
    with open(receipt, encoding="utf-8") as fh:
        data = json.load(fh)
    assert data["signature_scheme"] == "none"
    assert data["content_hash"] == "" and data["signature"] == ""


def test_missing_input_is_error(tmp_path):
    assert main(["capture", "--from", "litellm", "--in", str(tmp_path / "nope.jsonl"),
                 "--out", str(tmp_path / "o.jsonl")]) != EXIT_OK
