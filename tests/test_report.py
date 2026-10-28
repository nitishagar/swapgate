"""G0: report rendering tests."""

from swapgate.receipt import build_receipt_body, sign_receipt
from swapgate.report import to_html, to_markdown


def _receipt():
    body = build_receipt_body(
        {"suite": "demo", "suite_version": "0.1.0", "n_cases": 1, "judge": "deterministic",
         "baseline": "mock:parity", "candidate": "mock:regress",
         "baseline_pass_rate": 1.0, "candidate_pass_rate": 0.0,
         "regression_gap": 1.0, "fail_under": 0.5, "max_regression": 0.02,
         "passed": False, "regressed_case_ids": ["c1"]},
        [{"case_id": "c1",
          "baseline_output": "fine", "baseline_verdict": {"passed": True, "label": "pass"},
          "candidate_output": "<script>alert(1)</script>", "candidate_verdict": {"passed": False, "label": "fail"},
          "regressed": True}],
    )
    return sign_receipt(body, b"key")


def test_markdown_receipt_contents():
    text = to_markdown(_receipt())
    assert "# Swap receipt: FAIL" in text
    assert "mock:parity" in text and "mock:regress" in text
    assert "| `c1` | pass | fail | yes |" in text
    assert "swapgate verify" in text


def test_markdown_pass_verdict():
    receipt = _receipt()
    receipt["summary"]["passed"] = True
    assert "# Swap receipt: PASS" in to_markdown(receipt)


def test_html_escapes_outputs():
    page = to_html(_receipt())
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;" in page
    assert "Swap receipt: FAIL" in page
    assert "content_hash" not in page  # field shown as `hash ...`
    assert "hash " in page
