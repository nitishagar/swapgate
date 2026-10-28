"""Deterministic judge: exact / contains / regex / length / json-keys checks.

Every rubric check must pass (AND). Score = fraction of checks passed.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .base import Verdict


def run_check(output: str, check: dict[str, Any]) -> tuple[bool, str]:
    kind = check.get("type", "")
    if kind == "exact":
        ok = output.strip() == str(check.get("value", "")).strip()
        return ok, "exact match" if ok else "output differs from expected"
    if kind == "contains":
        values = check.get("values", [check.get("value", "")])
        missing = [v for v in values if str(v) not in output]
        return not missing, "all substrings present" if not missing else f"missing: {missing}"
    if kind == "not_contains":
        values = check.get("values", [check.get("value", "")])
        present = [v for v in values if str(v) in output]
        return not present, "no forbidden substrings" if not present else f"forbidden present: {present}"
    if kind == "regex":
        ok = re.search(str(check.get("pattern", "")), output) is not None
        return ok, "pattern matched" if ok else f"pattern not found: {check.get('pattern')}"
    if kind == "min_length":
        ok = len(output) >= int(check.get("value", 0))
        return ok, f"len {len(output)} >= {check.get('value')}" if ok else f"too short: {len(output)}"
    if kind == "max_length":
        ok = len(output) <= int(check.get("value", 10**9))
        return ok, f"len {len(output)} <= {check.get('value')}" if ok else f"too long: {len(output)}"
    if kind == "json_keys":
        try:
            parsed = json.loads(output)
        except (json.JSONDecodeError, ValueError):
            return False, "output is not JSON"
        if not isinstance(parsed, dict):
            return False, "JSON output is not an object"
        missing = [k for k in check.get("keys", []) if k not in parsed]
        return not missing, "required keys present" if not missing else f"missing keys: {missing}"
    return False, f"unknown check type: {kind}"


class DeterministicJudge:
    name = "deterministic"

    def evaluate(self, output: str, case: Any) -> Verdict:
        rubric = getattr(case, "rubric", []) or []
        if not rubric:
            return Verdict(passed=True, score=1.0, rationale="no checks; vacuous pass")
        results = [run_check(output, check) for check in rubric]
        passed = all(ok for ok, _ in results)
        score = sum(1 for ok, _ in results if ok) / len(results)
        notes = "; ".join(note for _, note in results)
        return Verdict(
            passed=passed,
            score=score,
            probability=1.0 if passed else 0.0,
            rationale=f"{sum(1 for ok, _ in results if ok)}/{len(results)} checks passed: {notes}",
        )
