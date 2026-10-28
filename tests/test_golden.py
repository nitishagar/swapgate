"""G1: golden receipt — byte-stable apart from volatile fields."""

import json
import os

from swapgate.cli import EXIT_OK, main
from swapgate.evals import EvalCase, EvalSuite, save_suite

GOLDEN = os.path.join(os.path.dirname(__file__), "golden", "receipt.json")
VOLATILE = {"issued_at", "content_hash", "signature", "signature_scheme"}


def _fixed_suite(path: str) -> None:
    save_suite(EvalSuite(name="golden", version="0.1.0", cases=[
        EvalCase(id="golden-1",
                 input=[{"role": "user", "content": "Summarise the refund policy for delayed flights"}],
                 rubric=[{"type": "contains", "values": ["refund", "policy"]},
                         {"type": "min_length", "value": 30}],
                 tags=["golden"]),
        EvalCase(id="golden-2",
                 input=[{"role": "user", "content": "Explain baggage allowance rules clearly"}],
                 rubric=[{"type": "contains", "values": ["baggage", "allowance"]},
                         {"type": "min_length", "value": 30}],
                 tags=["golden"]),
    ]), path)


def _normalized(receipt: dict) -> dict:
    return {k: v for k, v in receipt.items() if k not in VOLATILE}


def test_golden_receipt_matches(tmp_path):
    suite = str(tmp_path / "suite.json")
    _fixed_suite(suite)
    receipt_path = str(tmp_path / "receipt.json")
    code = main(["compare", "--suite", suite, "--baseline", "mock:parity",
                 "--candidate", "mock:seed-7", "--fail-under", "0.5",
                 "--max-regression", "0.5", "--out", receipt_path,
                 "--key", str(tmp_path / "key")])
    assert code == EXIT_OK
    with open(receipt_path, encoding="utf-8") as fh:
        receipt = json.load(fh)
    with open(GOLDEN, encoding="utf-8") as fh:
        golden = json.load(fh)
    assert _normalized(receipt) == golden
