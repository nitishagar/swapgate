"""Typed-decision judge: choice + probability, with pluggable backends.

Verdict labels are constrained to pass | fail | needs_review with an explicit
probability, so downstream gates can threshold on confidence. The local backend
combines deterministic signals offline; remote typed-decision backends
plug in behind the same protocol for live runs.
"""

from __future__ import annotations

from typing import Any, Protocol

from .base import Verdict
from .deterministic import DeterministicJudge


class TypedBackend(Protocol):
    name: str

    def decide(self, output: str, case: Any) -> Verdict:
        ...


class LocalHeuristicBackend:
    """Offline backend: deterministic checks mapped onto typed labels."""

    name = "local"

    def __init__(self, review_band: tuple[float, float] = (0.4, 0.7)):
        self.judge = DeterministicJudge()
        self.review_band = review_band

    def decide(self, output: str, case: Any) -> Verdict:
        verdict = self.judge.evaluate(output, case)
        lo, hi = self.review_band
        if verdict.score >= hi:
            return Verdict(passed=True, score=verdict.score, label="pass",
                            probability=verdict.score, rationale=verdict.rationale)
        if verdict.score < lo:
            return Verdict(passed=False, score=verdict.score, label="fail",
                            probability=1.0 - verdict.score, rationale=verdict.rationale)
        return Verdict(passed=False, score=verdict.score, label="needs_review",
                        probability=0.5, rationale=f"borderline ({verdict.rationale})")


class TypedJudge:
    name = "typed"

    def __init__(self, backend: TypedBackend | None = None):
        self.backend = backend or LocalHeuristicBackend()

    def evaluate(self, output: str, case: Any) -> Verdict:
        return self.backend.decide(output, case)
