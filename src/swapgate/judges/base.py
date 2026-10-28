"""Judge protocol and typed verdicts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class Verdict:
    passed: bool
    score: float  # 0.0 - 1.0
    label: str = ""  # pass | fail | needs_review
    probability: float = 1.0  # judge confidence in `passed`
    rationale: str = ""

    def __post_init__(self) -> None:
        if not self.label:
            self.label = "pass" if self.passed else "fail"

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "score": self.score,
            "label": self.label,
            "probability": self.probability,
            "rationale": self.rationale,
        }


class Judge(Protocol):
    name: str

    def evaluate(self, output: str, case: Any) -> Verdict:
        ...
