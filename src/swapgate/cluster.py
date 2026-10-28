"""Offline trace clustering: template signatures + shingle Jaccard, no embeddings.

`cluster_events` groups traces by structural template (numbers, quoted spans
and pseudonyms slotified), then merges near-duplicate templates by Jaccard
similarity over word shingles. Deterministic; stable across runs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .traces import TraceEvent, last_user_text

_SLOT_PATTERNS = [
    (re.compile(r"<[A-Z_]+_[0-9a-f]{6}>"), " <PII> "),
    (re.compile(r'"[^"]{1,80}"'), ' "STR" '),
    (re.compile(r"'[^']{1,80}'"), " 'STR' "),
    (re.compile(r"\b\d[\d,._-]*\b"), " <NUM> "),
]


def template_signature(text: str) -> str:
    collapsed = re.sub(r"\s+", " ", text.strip().lower())
    for pattern, slot in _SLOT_PATTERNS:
        collapsed = pattern.sub(slot, collapsed)
    return re.sub(r"\s+", " ", collapsed).strip()


def _shingles(text: str, n: int = 2) -> set[str]:
    words = text.split()
    if len(words) < n:
        return {" ".join(words)} if words else set()
    return {" ".join(words[i:i + n]) for i in range(len(words) - n + 1)}


def jaccard(a: str, b: str) -> float:
    sa, sb = _shingles(a), _shingles(b)
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


@dataclass
class Cluster:
    template: str
    members: list[int] = field(default_factory=list)  # indexes into the event list
    exemplar: str = ""


def cluster_events(
    events: list[TraceEvent],
    max_clusters: int = 8,
    merge_threshold: float = 0.5,
) -> list[Cluster]:
    """Group events into at most max_clusters clusters (deterministic)."""
    by_template: dict[str, Cluster] = {}
    order: list[str] = []
    for idx, event in enumerate(events):
        sig = template_signature(last_user_text(event.messages))
        if sig not in by_template:
            by_template[sig] = Cluster(template=sig)
            order.append(sig)
        by_template[sig].members.append(idx)
    clusters = [by_template[sig] for sig in order]

    merged: list[Cluster] = []
    for cluster in sorted(clusters, key=lambda c: (-len(c.members), c.template)):
        placed = False
        for target in merged:
            if jaccard(cluster.template, target.template) >= merge_threshold:
                target.members.extend(cluster.members)
                placed = True
                break
        if not placed:
            merged.append(cluster)

    merged.sort(key=lambda c: (-len(c.members), c.template))
    if len(merged) > max_clusters:
        overflow: list[int] = []
        for extra in merged[max_clusters:]:
            overflow.extend(extra.members)
        merged = merged[:max_clusters]
        if overflow:
            merged.append(Cluster(template="<overflow: long tail>", members=sorted(overflow)))

    for cluster in merged:
        first = min(cluster.members)
        cluster.exemplar = last_user_text(events[first].messages)
        cluster.members.sort()
    return merged
