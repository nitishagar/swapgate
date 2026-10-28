"""G0: runner + provider tests (mock offline; live marked)."""

import asyncio
import os

import pytest

from swapgate.evals import EvalCase
from swapgate.runner import MockProvider, OpenAICompatProvider, parse_provider, replay


def _case(text: str) -> EvalCase:
    return EvalCase(id="c", input=[{"role": "user", "content": text}])


def _run(provider, text="Summarise the refund policy"):
    return asyncio.run(provider.complete([{"role": "user", "content": text}]))


def test_mock_parity_echoes_keywords():
    out = _run(MockProvider("parity"))
    assert "refund" in out and "policy" in out


def test_mock_regress_is_refusal():
    out = _run(MockProvider("regress"))
    assert out == "I cannot answer that."


def test_unknown_mock_scenario_falls_through_to_parity():
    text = "Summarise the refund policy"
    assert _run(MockProvider("bogus"), text) == _run(MockProvider("parity"), text)
    assert MockProvider("bogus").label == "mock:bogus"


def test_mock_seed_is_deterministic_and_distinct():
    a = _run(MockProvider("seed-1"))
    b = _run(MockProvider("seed-1"))
    c = _run(MockProvider("seed-2"))
    assert a == b
    assert a != c


def test_parse_provider_specs():
    assert parse_provider("mock:parity").label == "mock:parity"
    p = parse_provider("openai-compat:https://x.example/v1|model-z")
    assert isinstance(p, OpenAICompatProvider)
    assert p.model == "model-z"
    with pytest.raises(ValueError):
        parse_provider("openai-compat:missing-model")
    with pytest.raises(ValueError):
        parse_provider("telepathy:v1")


def test_replay_preserves_case_order():
    cases = [EvalCase(id=f"c{i}", input=[{"role": "user", "content": f"topic {i}"}]) for i in range(5)]
    results = asyncio.run(replay(cases, MockProvider("parity"), concurrency=2))
    assert [r.case_id for r in results] == [f"c{i}" for i in range(5)]
    assert all(r.output for r in results)


@pytest.mark.live
def test_live_openai_compat_endpoint():
    if os.environ.get("SWAPGATE_LIVE") != "1":
        pytest.skip("SWAPGATE_LIVE=1 not set")
    base = os.environ.get("SWAPGATE_BASE_URL", "")
    model = os.environ.get("SWAPGATE_MODEL", "")
    if not base or not model:
        pytest.skip("SWAPGATE_BASE_URL/SWAPGATE_MODEL not set")
    out = _run(OpenAICompatProvider(base, model), "Reply with exactly: alive")
    assert out.strip()
