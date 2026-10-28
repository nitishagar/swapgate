"""G0: clustering unit tests."""

from swapgate.cluster import cluster_events, jaccard, template_signature
from swapgate.traces import TraceEvent


def _ev(text: str, tid: str = "t") -> TraceEvent:
    return TraceEvent(trace_id=tid, model="m",
                      messages=[{"role": "user", "content": text}])


def test_template_signature_slotifies_numbers():
    assert template_signature("Refund order 42 now") == template_signature("Refund order 1337 now")


def test_jaccard_identical_and_disjoint():
    assert jaccard("a b c d", "a b c d") == 1.0
    assert jaccard("a b c", "x y z") == 0.0


def test_similar_prompts_cluster_together():
    events = [
        _ev("Summarise the refund policy for delayed flights", "a"),
        _ev("Summarise the refund policy for cancelled flights", "b"),
        _ev("Draft a GST notice reply for notice 9912", "c"),
    ]
    clusters = cluster_events(events, max_clusters=8)
    assert len(clusters) == 2
    sizes = sorted(len(c.members) for c in clusters)
    assert sizes == [1, 2]
    assert clusters[0].exemplar.startswith("Summarise")


def test_clustering_is_deterministic():
    events = [_ev(f"Refund status for order {i}") for i in range(10)]
    first = [(c.template, c.members) for c in cluster_events(events)]
    second = [(c.template, c.members) for c in cluster_events(events)]
    assert first == second


def test_overflow_bucket_when_over_max():
    topics = [
        "refund policy for delayed flights",
        "baggage allowance on international routes",
        "gst notice reply drafting help",
        "passport renewal appointment slots",
        "upip autopay failure complaint draft",
        "train ticket cancellation charges",
    ]
    events = [_ev(t) for t in topics]
    clusters = cluster_events(events, max_clusters=2)
    assert len(clusters) == 3
    assert clusters[-1].template.startswith("<overflow")
