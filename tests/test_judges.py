"""G0+G3: judge tests (deterministic fixtures + recorded LLM fixtures)."""

import pytest

from swapgate.evals import EvalCase
from swapgate.judges import (
    DeterministicJudge,
    FixtureCompleter,
    LLMJudge,
    LocalHeuristicBackend,
    TypedJudge,
)


def _case(rubric):
    return EvalCase(id="c", input=[], rubric=rubric, expected="")


JUDGE = DeterministicJudge()


def test_exact():
    assert JUDGE.evaluate("abc", _case([{"type": "exact", "value": "abc"}])).passed
    assert not JUDGE.evaluate("abd", _case([{"type": "exact", "value": "abc"}])).passed


def test_contains_and_not_contains():
    assert JUDGE.evaluate("the refund policy", _case([{"type": "contains", "values": ["refund", "policy"]}])).passed
    assert not JUDGE.evaluate("the policy", _case([{"type": "contains", "values": ["refund"]}])).passed
    assert JUDGE.evaluate("clean text", _case([{"type": "not_contains", "value": "secret"}])).passed
    assert not JUDGE.evaluate("has secret", _case([{"type": "not_contains", "value": "secret"}])).passed


def test_regex_and_lengths():
    assert JUDGE.evaluate("order ORD-42", _case([{"type": "regex", "pattern": r"ORD-\d+"}])).passed
    assert JUDGE.evaluate("long enough output", _case([{"type": "min_length", "value": 5}])).passed
    assert not JUDGE.evaluate("tiny", _case([{"type": "min_length", "value": 50}])).passed
    assert JUDGE.evaluate("tiny", _case([{"type": "max_length", "value": 50}])).passed


def test_json_keys():
    assert JUDGE.evaluate('{"a": 1}', _case([{"type": "json_keys", "keys": ["a"]}])).passed
    assert not JUDGE.evaluate('{"a": 1}', _case([{"type": "json_keys", "keys": ["b"]}])).passed
    assert not JUDGE.evaluate("not json", _case([{"type": "json_keys", "keys": ["a"]}])).passed


def test_unknown_check_fails():
    v = JUDGE.evaluate("x", _case([{"type": "telepathy"}]))
    assert not v.passed


def test_empty_rubric_vacuous_pass():
    v = JUDGE.evaluate("", _case([]))
    assert v.passed and v.score == 1.0


def test_score_is_fraction_passed():
    v = JUDGE.evaluate("refund only", _case([
        {"type": "contains", "value": "refund"},
        {"type": "contains", "value": "policy"},
    ]))
    assert not v.passed
    assert v.score == 0.5


def _llm_with(recording: str, output: str = "the refund policy"):
    case = _case([{"type": "contains", "value": "refund"}])
    prompt = LLMJudge(FixtureCompleter({})).render_prompt(output, case)
    return LLMJudge(FixtureCompleter({prompt: recording})), case


def test_llm_judge_pass_parses():
    judge, case = _llm_with("PASS 0.9 mentions refund policy")
    v = judge.evaluate("the refund policy", case)
    assert v.passed and v.score == 0.9 and v.label == "pass"


def test_llm_judge_fail_parses():
    judge, case = _llm_with("FAIL 0.2 missing refund mention", output="unrelated")
    v = judge.evaluate("unrelated", case)
    assert not v.passed and v.label == "fail"


def test_llm_judge_unparseable_needs_review():
    judge, case = _llm_with("maybe, I think so?", output="whatever")
    v = judge.evaluate("whatever", case)
    assert not v.passed and v.label == "needs_review"


def test_llm_judge_unknown_prompt_raises():
    judge = LLMJudge(FixtureCompleter({}))
    with pytest.raises(KeyError):
        judge.evaluate("x", _case([]))


def test_llm_judge_called_once():
    judge, case = _llm_with("PASS 1.0 yes")
    judge.evaluate("the refund policy", case)
    assert len(judge.completer.calls) == 1


def test_typed_labels():
    judge = TypedJudge(LocalHeuristicBackend())
    passing = judge.evaluate("refund policy text", _case([{"type": "contains", "values": ["refund", "policy"]}]))
    assert passing.label == "pass" and passing.passed
    failing = judge.evaluate("zzzz", _case([{"type": "contains", "values": ["refund", "policy"]}]))
    assert failing.label == "fail" and not failing.passed


def test_typed_review_band():
    judge = TypedJudge(LocalHeuristicBackend(review_band=(0.4, 0.7)))
    v = judge.evaluate("refund only", _case([
        {"type": "contains", "value": "refund"},
        {"type": "contains", "value": "policy"},
    ]))
    assert v.score == 0.5
    assert v.label == "needs_review" and not v.passed
