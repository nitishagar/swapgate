"""Generate swap report 001 (manual script; needs the [e2e] extra).

Reuses tests/e2e/litellm_harness.py: local LiteLLM mock traces flow through the
real CLI (capture → build/approve → compare → report). Mock providers prove the
gate mechanics; no live-model claims are made.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO / "tests" / "e2e"))

from litellm_harness import run_local_traces, write_rows  # noqa: E402

CLI = [sys.executable, "-m", "swapgate.cli"]

PROLOGUE = """\
# Swap report 001: support-desk rehearsal (mock providers)

Methodology: traces produced by in-process LiteLLM (`mock_response`, telemetry
off), ingested via `capture --from litellm`, clustered into an eval suite,
human-approved, then replayed with `compare --baseline mock:parity
--candidate mock:seed-3`. Mock providers prove gate mechanics only; this report
makes no claims about any real model. Reproduce with
`examples/swap-reports/generate.py`.

## Live rerun (documented, not executed)

To replay the same suite against live OpenAI-compatible endpoints instead of
mocks, export `SWAPGATE_API_KEY` and replace the `compare` step with e.g.:

    swapgate compare --suite s.json \\
      --baseline "openai-compat:https://api.vendor-a.example/v1|model-a" \\
      --candidate "openai-compat:https://api.vendor-b.example/v1|model-b" \\
      --fail-under 0.8 --max-regression 0.1 --out r.json --report report.md

No live run was performed for this report; the numbers below are mock-only.
"""


def _run(argv: list[str]) -> None:
    proc = subprocess.run(CLI + argv, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise SystemExit(f"{' '.join(argv)} failed:\n{proc.stdout}\n{proc.stderr}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-md", default=str(HERE / "001-open-weights.md"))
    parser.add_argument("--out-html",
                        default=str(REPO / "docs" / "reports" / "001-open-weights.html"))
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        traces = f"{tmp}/traces.jsonl"
        write_rows(run_local_traces(), traces)
        events, suite, receipt = f"{tmp}/e.jsonl", f"{tmp}/s.json", f"{tmp}/r.json"
        _run(["capture", "--from", "litellm", "--in", traces, "--out", events])
        _run(["build-evals", "--in", events, "--out", suite, "--name", "report-001"])
        _run(["build-evals", "--out", suite, "--approve"])
        report_md = f"{tmp}/report.md"
        _run(["compare", "--suite", suite, "--baseline", "mock:parity",
              "--candidate", "mock:seed-3", "--fail-under", "0.0",
              "--max-regression", "0.5", "--out", receipt, "--report", report_md])
        report_html = f"{tmp}/report.html"
        _run(["report", "--receipt", receipt, "--format", "html", "--out", report_html])
        md_text = PROLOGUE + "\n" + Path(report_md).read_text(encoding="utf-8")
        Path(args.out_md).write_text(md_text, encoding="utf-8")
        html_path = Path(args.out_html)
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_text(Path(report_html).read_text(encoding="utf-8"), encoding="utf-8")
    print(f"wrote {args.out_md} and {args.out_html}")


if __name__ == "__main__":
    main()
