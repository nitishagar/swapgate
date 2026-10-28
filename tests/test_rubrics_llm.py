"""P2: LLM-synthesised rubric tests (recorded fixtures, no network)."""

import asyncio

import pytest

from swapgate.cluster import Cluster, cluster_events
from swapgate.evals import build_suite
from swapgate.judges.llm import FixtureCompleter
from swapgate.rubrics_llm import (
    ProviderCompleter,
    complete_sync,
    is_valid_check,
    render_rubric_prompt,
    synthesize_rubric_llm,
)
from swapgate.traces import TraceEvent


def _cluster() -> Cluster:
    events = [TraceEvent(trace_id="t", model="m",
                         messages=[{"role": "user", "content": "Summarise the refund policy"}])]
    return cluster_events(events)[0]


def test_valid_synthesis_keeps_base_plus_checks():
    cluster = _cluster()
    prompt = render_rubric_prompt(cluster.template, cluster.exemplar)
    canned = ('[{"type": "contains", "values": ["refund"]}, '
              '{"type": "min_length", "value": 20}]')
    rubric = synthesize_rubric_llm(cluster, FixtureCompleter({prompt: canned}))
    assert rubric[0] == {"type": "min_length", "value": 1}
    assert {"type": "contains", "values": ["refund"]} in rubric
    assert {"type": "min_length", "value": 20} in rubric


def test_invalid_checks_dropped():
    cluster = _cluster()
    prompt = render_rubric_prompt(cluster.template, cluster.exemplar)
    canned = ('[{"type": "telepathy"}, {"type": "contains"}, '
              '{"type": "min_length", "value": "lots"}, {"type": "regex"}, '
              '"not-a-dict", {"type": "contains", "values": ["ok"]}]')
    rubric = synthesize_rubric_llm(cluster, FixtureCompleter({prompt: canned}))
    assert rubric == [{"type": "min_length", "value": 1},
                      {"type": "contains", "values": ["ok"]}]


def test_unparseable_output_yields_base_only():
    cluster = _cluster()
    prompt = render_rubric_prompt(cluster.template, cluster.exemplar)
    rubric = synthesize_rubric_llm(cluster, FixtureCompleter({prompt: "no json here"}))
    assert rubric == [{"type": "min_length", "value": 1}]


def test_check_vocabulary_validation():
    assert is_valid_check({"type": "exact", "value": "a"})
    assert is_valid_check({"type": "contains", "value": "a"})
    assert is_valid_check({"type": "not_contains", "values": ["a"]})
    assert is_valid_check({"type": "regex", "pattern": "a+"})
    assert is_valid_check({"type": "max_length", "value": 5})
    assert is_valid_check({"type": "json_keys", "keys": ["a"]})
    assert not is_valid_check({"type": "min_length", "value": True})
    assert not is_valid_check({"type": "json_keys", "keys": "a"})
    assert not is_valid_check({"type": "nope"})
    assert not is_valid_check("x")


def test_bridge_awaits_async_provider():
    class FakeAsync:
        async def complete(self, messages):
            await asyncio.sleep(0)
            return "bridged"

    assert complete_sync(FakeAsync(), []) == "bridged"
    assert isinstance(ProviderCompleter(FakeAsync()).complete("hi"), str)


def test_build_suite_llm_wiring_and_default_untouched():
    events = [TraceEvent(trace_id="t", model="m",
                         messages=[{"role": "user", "content": "Summarise the refund policy"}])]
    cluster = cluster_events(events)[0]
    prompt = render_rubric_prompt(cluster.template, cluster.exemplar)
    canned = '[{"type": "contains", "values": ["refund"]}]'
    suite = build_suite("w", events, rubric_source="llm",
                        rubric_completer=FixtureCompleter({prompt: canned}))
    assert suite.cases[0].rubric[1] == {"type": "contains", "values": ["refund"]}
    default = build_suite("w", events)
    assert default.cases[0].rubric[0] == {"type": "min_length", "value": 1}
    with pytest.raises(ValueError):
        build_suite("w", events, rubric_source="llm")
    with pytest.raises(ValueError):
        build_suite("w", events, rubric_source="telepathy")
