"""Eval suites: schema, heuristic rubric synthesis, human approval gate.

Rubrics are synthesised offline from cluster templates (heuristic checks).
An LLM-authored rubric pass is a live-only upgrade; the suite format is the
same either way. Nothing becomes a runnable suite until a human approves it:
`build-evals` writes `<out>.pending.json`; `--approve` finalises it.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from .cluster import Cluster, cluster_events
from .traces import TraceEvent, last_user_text


@dataclass
class EvalCase:
    id: str
    input: list[dict[str, str]]
    rubric: list[dict[str, Any]] = field(default_factory=list)
    expected: str = ""
    tags: list[str] = field(default_factory=list)
    source_trace_ids: list[str] = field(default_factory=list)


@dataclass
class EvalSuite:
    name: str
    version: str = "0.1.0"
    cases: list[EvalCase] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "cases": [asdict(c) for c in self.cases],
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvalSuite":
        return cls(
            name=str(data.get("name", "suite")),
            version=str(data.get("version", "0.1.0")),
            cases=[EvalCase(**c) for c in data.get("cases", [])],
            metadata=dict(data.get("metadata", {})),
        )


def save_suite(suite: EvalSuite, path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(suite.to_dict(), fh, ensure_ascii=False, indent=2, sort_keys=True)


def load_suite(path: str) -> EvalSuite:
    with open(path, encoding="utf-8") as fh:
        return EvalSuite.from_dict(json.load(fh))


def pending_path_for(out_path: str) -> str:
    return out_path + ".pending.json" if not out_path.endswith(".json") else out_path.replace(".json", ".pending.json")


def synthesize_rubric(cluster: Cluster, exemplar_output: str = "") -> list[dict[str, Any]]:
    """Heuristic checks derived from the cluster template. Review before use."""
    rubric: list[dict[str, Any]] = [{"type": "min_length", "value": 1}]
    words = [w for w in cluster.template.split() if len(w) > 4 and not w.startswith("<")]
    for word in words[:3]:
        rubric.append({"type": "contains", "value": word.strip(".,:;!?\"'")})
    if exemplar_output:
        rubric.append({"type": "max_length", "value": max(64, len(exemplar_output) * 3)})
    return rubric


def build_suite_from_clusters(
    name: str,
    events: list[TraceEvent],
    clusters: list[Cluster],
    cases_per_cluster: int = 2,
) -> EvalSuite:
    cases: list[EvalCase] = []
    for ci, cluster in enumerate(clusters):
        for member in cluster.members[:cases_per_cluster]:
            event = events[member]
            cases.append(EvalCase(
                id=f"{name}-c{ci:02d}-{member:04d}",
                input=[dict(m) for m in event.messages],
                rubric=synthesize_rubric(cluster, event.output),
                expected=event.output,
                tags=[f"cluster:{ci}"],
                source_trace_ids=[event.trace_id],
            ))
    return EvalSuite(name=name, cases=cases, metadata={"clusters": len(clusters)})


def build_suite(name: str, events: list[TraceEvent], max_clusters: int = 8) -> EvalSuite:
    return build_suite_from_clusters(name, events, cluster_events(events, max_clusters))


class ApprovalRequiredError(Exception):
    pass


def finalize_pending(pending_path: str, out_path: str, approved: bool) -> EvalSuite:
    """Finalise a pending suite. Raises unless the human review flag is set."""
    if not approved:
        raise ApprovalRequiredError(
            f"human review required: inspect {pending_path}, then re-run with --approve"
        )
    suite = load_suite(pending_path)
    save_suite(suite, out_path)
    return suite
