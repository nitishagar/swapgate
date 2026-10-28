"""Baseline-vs-candidate comparison and the regression rule.

Both providers replay every case; the judge scores both. The candidate fails
the gate when its pass rate is below `fail_under` (absolute quality floor)
or when it drops more than `max_regression` below the baseline (relative rule).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from .judges.base import Verdict
from .runner import Provider, replay


@dataclass
class CaseComparison:
    case_id: str
    baseline_output: str
    baseline_verdict: Verdict
    candidate_output: str
    candidate_verdict: Verdict

    @property
    def regressed(self) -> bool:
        return self.baseline_verdict.passed and not self.candidate_verdict.passed

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "baseline_output": self.baseline_output,
            "baseline_verdict": self.baseline_verdict.to_dict(),
            "candidate_output": self.candidate_output,
            "candidate_verdict": self.candidate_verdict.to_dict(),
            "regressed": self.regressed,
        }


@dataclass
class ComparisonResult:
    suite_name: str
    suite_version: str
    baseline_label: str
    candidate_label: str
    judge_name: str
    cases: list[CaseComparison] = field(default_factory=list)
    fail_under: float = 0.0
    max_regression: float = 1.0

    @property
    def baseline_pass_rate(self) -> float:
        if not self.cases:
            return 1.0
        return sum(1 for c in self.cases if c.baseline_verdict.passed) / len(self.cases)

    @property
    def candidate_pass_rate(self) -> float:
        if not self.cases:
            return 1.0
        return sum(1 for c in self.cases if c.candidate_verdict.passed) / len(self.cases)

    @property
    def regression_gap(self) -> float:
        return self.baseline_pass_rate - self.candidate_pass_rate

    @property
    def passed(self) -> bool:
        if self.candidate_pass_rate < self.fail_under:
            return False
        return self.regression_gap <= self.max_regression

    def summary(self) -> dict[str, Any]:
        return {
            "suite": self.suite_name,
            "suite_version": self.suite_version,
            "baseline": self.baseline_label,
            "candidate": self.candidate_label,
            "judge": self.judge_name,
            "n_cases": len(self.cases),
            "baseline_pass_rate": round(self.baseline_pass_rate, 4),
            "candidate_pass_rate": round(self.candidate_pass_rate, 4),
            "regression_gap": round(self.regression_gap, 4),
            "fail_under": self.fail_under,
            "max_regression": self.max_regression,
            "passed": self.passed,
            "regressed_case_ids": [c.case_id for c in self.cases if c.regressed],
        }


async def compare_async(
    suite: Any,
    baseline: Provider,
    candidate: Provider,
    judge: Any,
    fail_under: float = 0.0,
    max_regression: float = 1.0,
    concurrency: int = 8,
) -> ComparisonResult:
    base_out, cand_out = await asyncio.gather(
        replay(suite.cases, baseline, concurrency),
        replay(suite.cases, candidate, concurrency),
    )
    by_id = {c.id: c for c in suite.cases}
    comparisons: list[CaseComparison] = []
    for b, c in zip(base_out, cand_out):
        case = by_id[b.case_id]
        comparisons.append(CaseComparison(
            case_id=b.case_id,
            baseline_output=b.output,
            baseline_verdict=judge.evaluate(b.output, case),
            candidate_output=c.output,
            candidate_verdict=judge.evaluate(c.output, case),
        ))
    comparisons.sort(key=lambda c: c.case_id)
    return ComparisonResult(
        suite_name=suite.name,
        suite_version=suite.version,
        baseline_label=baseline.label,
        candidate_label=candidate.label,
        judge_name=getattr(judge, "name", "unknown"),
        cases=comparisons,
        fail_under=fail_under,
        max_regression=max_regression,
    )


def compare(*args: Any, **kwargs: Any) -> ComparisonResult:
    return asyncio.run(compare_async(*args, **kwargs))
