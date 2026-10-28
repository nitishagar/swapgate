"""G2: regression-gate behaviour tests."""

from swapgate.compare import compare
from swapgate.evals import EvalCase, EvalSuite
from swapgate.judges import DeterministicJudge
from swapgate.runner import MockProvider

JUDGE = DeterministicJudge()


def _suite() -> EvalSuite:
    cases = [
        EvalCase(
            id=f"case-{i}",
            input=[{"role": "user", "content": text}],
            rubric=[
                {"type": "contains", "values": words},
                {"type": "min_length", "value": 30},
            ],
        )
        for i, (text, words) in enumerate([
            ("Summarise the refund policy for delayed flights", ["refund", "policy"]),
            ("Explain baggage allowance rules clearly", ["baggage", "allowance"]),
        ])
    ]
    return EvalSuite(name="gate", cases=cases)


def test_parity_passes_gate():
    result = compare(_suite(), MockProvider("parity"), MockProvider("parity"), JUDGE)
    assert result.passed
    assert result.candidate_pass_rate == 1.0
    assert result.regression_gap == 0.0


def test_regress_candidate_fails_absolute_floor():
    result = compare(_suite(), MockProvider("parity"), MockProvider("regress"), JUDGE,
                     fail_under=0.5)
    assert not result.passed
    assert result.candidate_pass_rate == 0.0
    assert len(result.summary()["regressed_case_ids"]) == 2


def test_regress_candidate_fails_relative_rule():
    result = compare(_suite(), MockProvider("parity"), MockProvider("regress"), JUDGE,
                     max_regression=0.02)
    assert not result.passed
    assert result.regression_gap == 1.0


def test_seed_variant_passes_lenient_gate():
    result = compare(_suite(), MockProvider("parity"), MockProvider("seed-7"), JUDGE,
                     fail_under=0.5, max_regression=0.5)
    assert result.passed


def test_empty_suite_passes_vacuously():
    result = compare(EvalSuite(name="empty"), MockProvider("parity"),
                     MockProvider("regress"), JUDGE)
    assert result.passed
