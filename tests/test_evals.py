"""G0: eval suite + approval gate tests."""

import pytest

from swapgate.cluster import cluster_events
from swapgate.evals import (
    ApprovalRequiredError,
    build_suite,
    build_suite_from_clusters,
    finalize_pending,
    load_suite,
    save_suite,
    synthesize_rubric,
)
from swapgate.traces import TraceEvent


def _ev(text: str, tid: str) -> TraceEvent:
    return TraceEvent(trace_id=tid, model="m",
                      messages=[{"role": "user", "content": text}],
                      output=f"output for {tid}")


def test_synthesize_rubric_has_checks():
    events = [_ev("Summarise the refund policy for delayed flights", "a")]
    cluster = cluster_events(events)[0]
    rubric = synthesize_rubric(cluster, "some output")
    kinds = [c["type"] for c in rubric]
    assert "min_length" in kinds and "contains" in kinds and "max_length" in kinds


def test_build_suite_assigns_ids_and_sources():
    events = [_ev(f"Refund status for order {i}", f"t{i}") for i in range(4)]
    suite = build_suite("demo", events, max_clusters=4)
    assert suite.name == "demo"
    assert len(suite.cases) >= 1
    assert all(c.id.startswith("demo-") for c in suite.cases)
    assert all(c.source_trace_ids for c in suite.cases)


def test_suite_roundtrip(tmp_path):
    events = [_ev("hello world", "a")]
    suite = build_suite("rt", events)
    path = str(tmp_path / "suite.json")
    save_suite(suite, path)
    loaded = load_suite(path)
    assert loaded.name == "rt"
    assert len(loaded.cases) == len(suite.cases)
    assert loaded.cases[0].id == suite.cases[0].id


def test_finalize_requires_approval(tmp_path):
    events = [_ev("hello world", "a")]
    suite = build_suite("g", events)
    pending = str(tmp_path / "g.pending.json")
    save_suite(suite, pending)
    with pytest.raises(ApprovalRequiredError):
        finalize_pending(pending, str(tmp_path / "g.json"), approved=False)


def test_finalize_with_approval_writes_suite(tmp_path):
    events = [_ev("hello world", "a")]
    suite = build_suite("g", events)
    pending = str(tmp_path / "g.pending.json")
    save_suite(suite, pending)
    out = str(tmp_path / "g.json")
    finalize_pending(pending, out, approved=True)
    assert load_suite(out).name == "g"


def test_cases_per_cluster_limit():
    events = [_ev(f"Refund status for order {i}", f"t{i}") for i in range(10)]
    clusters = cluster_events(events, max_clusters=1)
    suite = build_suite_from_clusters("lim", events, clusters, cases_per_cluster=2)
    assert len(suite.cases) == 2
