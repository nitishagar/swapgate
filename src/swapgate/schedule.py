"""Interval-based scheduled regressions.

Reads a schedules file, runs due entries through `compare()`, and records
every completed run (plus provider-exception failures) in the append-only
history. Unapproved suites and unknown judges refuse with exit 1 and no row.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from typing import Any

from . import history
from .compare import compare
from .evals import load_suite
from .judges import get_judge
from .receipt import build_receipt_body
from .runner import parse_provider

DEFAULT_SCHEDULES_PATH = "./schedules.json"


def load_schedules(path: str) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    entries = data.get("schedules", data) if isinstance(data, dict) else data
    if not isinstance(entries, list):
        raise ValueError(f"bad schedules file (want a list or {{schedules: [...]}}): {path}")
    return entries


def entry_due(entry: dict[str, Any], now: float | None = None) -> bool:
    """Missing last_run means due immediately."""
    last_run = entry.get("last_run")
    if last_run is None:
        return True
    interval = float(entry.get("interval_hours", 24))
    return (now if now is not None else time.time()) - float(last_run) >= interval * 3600


def _save_schedules(path: str, entries: list[dict[str, Any]]) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"schedules": entries}, fh, ensure_ascii=False, indent=2, sort_keys=True)
    os.replace(tmp, path)


def _still_due(schedules_path: str, key: tuple[str, str, str], now: float) -> bool:
    """Re-read due-state under the claim (closes the check-then-act race)."""
    try:
        entries = load_schedules(schedules_path)
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        return True
    for fresh in entries:
        if (fresh.get("suite"), fresh.get("baseline", "mock:parity"),
                fresh.get("candidate", "mock:parity")) == key:
            return entry_due(fresh, now)
    return True


def _unsigned_receipt(summary: dict[str, Any], cases: list[dict[str, Any]]) -> dict[str, Any]:
    """CLI-equivalent unsigned receipt shape (hash/signature empty, 'none')."""
    return {**build_receipt_body(summary, cases),
            "content_hash": "", "signature": "", "signature_scheme": "none"}


def run_entry(entry: dict[str, Any], history_path: str) -> dict[str, Any]:
    """Run one due entry; returns {status, ...} with status pass|fail|error."""
    suite_path = entry["suite"]
    if suite_path.endswith(".pending.json"):
        return {"status": "error", "error": f"refusing unapproved suite: {suite_path}"}
    suite = load_suite(suite_path)
    if not suite.metadata.get("approved"):
        return {"status": "error", "error": f"refusing unapproved suite: {suite_path}"}
    try:
        judge = get_judge(entry.get("judge", "deterministic"),
                          entry.get("judge_fixtures", ""))
        baseline = parse_provider(entry.get("baseline", "mock:parity"))
        candidate = parse_provider(entry.get("candidate", "mock:parity"))
    except ValueError as exc:
        return {"status": "error", "error": str(exc)}
    fail_under = float(entry.get("fail_under", 0.0))
    max_regression = float(entry.get("max_regression", 1.0))
    try:
        result = compare(suite, baseline, candidate, judge,
                         fail_under=fail_under, max_regression=max_regression)
    except Exception as exc:  # noqa: BLE001 — provider/judge failures become rows
        history.append_run(history_path, {
            "suite": suite_path, "baseline": baseline.label, "candidate": candidate.label,
            "judge": getattr(judge, "name", "unknown"),
            "fail_under": fail_under, "max_regression": max_regression,
            "receipt": None, "error": f"{type(exc).__name__}: {exc}"[:500],
        })
        return {"status": "error", "error": str(exc)[:200]}
    receipt = _unsigned_receipt(result.summary(), [c.to_dict() for c in result.cases])
    summary = result.summary()
    history.append_run(history_path, {
        "suite": suite_path, "baseline": summary["baseline"], "candidate": summary["candidate"],
        "judge": summary["judge"], "fail_under": fail_under, "max_regression": max_regression,
        "passed": summary["passed"], "baseline_pass_rate": summary["baseline_pass_rate"],
        "candidate_pass_rate": summary["candidate_pass_rate"],
        "receipt": receipt, "error": None,
    })
    return {"status": "pass" if summary["passed"] else "fail", "receipt": receipt}


def run_due(schedules_path: str, history_path: str, force: bool = False,
            now: float | None = None) -> dict[str, Any]:
    """Run due entries. Returns {ran, passed, failed, errors, exit_code}."""
    entries = load_schedules(schedules_path)
    now = time.time() if now is None else now
    outcome: dict[str, Any] = {"ran": 0, "passed": 0, "failed": 0, "errors": []}
    for entry in entries:
        if not force and not entry_due(entry, now):
            continue
        bad = [f for f in ("baseline", "candidate")
               if not isinstance(entry.get(f, "mock:parity"), str)]
        if not isinstance(entry.get("suite"), str):
            bad = ["suite"] + bad
        if bad:
            # A NULL/non-string spec would fail the NOT NULL claim INSERT and
            # look like single-flight contention; refuse loudly instead.
            outcome["errors"].append(
                f"bad schedules entry ({', '.join(bad)} must be strings)")
            continue
        key = (entry["suite"], entry.get("baseline", "mock:parity"),
               entry.get("candidate", "mock:parity"))
        if not history.claim(history_path, *key, now=now):
            continue  # overlapping tick holds it
        try:
            if not force and not _still_due(schedules_path, key, now):
                continue  # a concurrent tick recorded a run first
            result = run_entry(entry, history_path)
            if result["status"] == "error":
                outcome["errors"].append(result["error"])
                continue  # last_run advances only after completed runs
            outcome["ran"] += 1
            outcome["passed" if result["status"] == "pass" else "failed"] += 1
            entry["last_run"] = now
            _save_schedules(schedules_path, entries)  # under claim, before release
        finally:
            history.release(history_path, *key)
    if outcome["errors"]:
        outcome["exit_code"] = 1
    elif outcome["failed"]:
        outcome["exit_code"] = 2
    else:
        outcome["exit_code"] = 0
    outcome["checked_at"] = datetime.now(timezone.utc).isoformat()
    return outcome
