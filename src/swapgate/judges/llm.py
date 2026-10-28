"""LLM-as-judge over any OpenAI-compatible completer.

The completer is injected, so tests use recorded fixtures and live runs use
real endpoints. The judge prompt asks for a single-line verdict that parses
without a second model call: `PASS <0-1 score> <rationale...>`.
"""

from __future__ import annotations

import re
from typing import Any, Protocol

from .base import Verdict

JUDGE_TEMPLATE = """You are a strict eval judge. Decide if the CANDIDATE OUTPUT satisfies every check.

CHECKS:
{checks}

EXPECTED (reference, may be empty):
{expected}

CANDIDATE OUTPUT:
{output}

Reply on ONE line: PASS <score 0.0-1.0> <short rationale>
or: FAIL <score 0.0-1.0> <short rationale>"""

_VERDICT_RE = re.compile(r"^(PASS|FAIL)\s+([0-9]*\.?[0-9]+)\s*(.*)$", re.IGNORECASE)


class Completer(Protocol):
    def complete(self, prompt: str) -> str:
        ...


class FixtureCompleter:
    """Recorded completer for offline tests: unknown prompts raise."""

    def __init__(self, mapping: dict[str, str]):
        self.mapping = mapping
        self.calls: list[str] = []

    def complete(self, prompt: str) -> str:
        self.calls.append(prompt)
        if prompt not in self.mapping:
            raise KeyError(f"no recorded fixture for prompt ({len(prompt)} chars)")
        return self.mapping[prompt]


class LLMJudge:
    name = "llm"

    def __init__(self, completer: Completer, pass_threshold: float = 0.5):
        self.completer = completer
        self.pass_threshold = pass_threshold

    def render_prompt(self, output: str, case: Any) -> str:
        rubric = getattr(case, "rubric", []) or []
        checks = "\n".join(f"- {c}" for c in rubric) or "- (no checks: accept any non-empty output)"
        return JUDGE_TEMPLATE.format(
            checks=checks,
            expected=getattr(case, "expected", "") or "(none)",
            output=output,
        )

    def evaluate(self, output: str, case: Any) -> Verdict:
        prompt = self.render_prompt(output, case)
        raw = self.completer.complete(prompt).strip()
        first = raw.splitlines()[0] if raw else ""
        match = _VERDICT_RE.match(first)
        if not match:
            return Verdict(passed=False, score=0.0, label="needs_review",
                            probability=0.0, rationale=f"unparseable judge output: {first[:120]}")
        word, score_raw, rationale = match.groups()
        try:
            score = max(0.0, min(1.0, float(score_raw)))
        except ValueError:
            score = 0.0
        passed = word.upper() == "PASS" and score >= self.pass_threshold
        return Verdict(passed=passed, score=score,
                        probability=score if passed else 1.0 - score,
                        rationale=rationale.strip() or word)
