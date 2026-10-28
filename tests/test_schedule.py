"""P3: scheduler tests (due logic, claims, refusals, identity, append-only)."""

import json
import os
import threading

from swapgate import history
from swapgate.cli import EXIT_ERROR, EXIT_GATE_FAIL, EXIT_OK, main
from swapgate.evals import EvalCase, EvalSuite, save_suite
from swapgate.schedule import entry_due, run_due


def _suite(path: str, approved: bool = True) -> str:
    suite = EvalSuite(name="sched", cases=[
        EvalCase(id="s1",
                 input=[{"role": "user", "content": "Summarise the refund policy"}],
                 rubric=[{"type": "contains", "values": ["refund", "policy"]}]),
    ])
    if approved:
        suite.metadata["approved"] = {"by": "human", "at": "2026-10-28T00:00:00+00:00"}
    save_suite(suite, path)
    return path


def _schedules(path: str, entries: list) -> str:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"schedules": entries}, fh)
    return path


def _entry(suite: str, **over):
    base = {"suite": suite, "baseline": "mock:parity", "candidate": "mock:parity",
            "judge": "deterministic", "interval_hours": 24}
    base.update(over)
    return base


def test_entry_due_logic():
    assert entry_due({}, now=1000.0)  # missing last_run → due
    assert entry_due({"last_run": 0, "interval_hours": 1}, now=7200.0)
    assert not entry_due({"last_run": 7000, "interval_hours": 1}, now=7200.0)


def test_run_due_pass_and_last_run_advances(tmp_path):
    suite = _suite(str(tmp_path / "s.json"))
    sched = _schedules(str(tmp_path / "sched.json"), [_entry(suite)])
    db = str(tmp_path / "r.db")
    outcome = run_due(sched, db, now=10000.0)
    assert outcome["exit_code"] == 0
    assert outcome["passed"] == 1
    with open(sched, encoding="utf-8") as fh:
        assert json.load(fh)["schedules"][0]["last_run"] == 10000.0
    assert len(history.list_runs(db)) == 1


def test_second_run_skips_as_not_due(tmp_path):
    suite = _suite(str(tmp_path / "s.json"))
    sched = _schedules(str(tmp_path / "sched.json"), [_entry(suite)])
    db = str(tmp_path / "r.db")
    run_due(sched, db, now=10000.0)
    outcome = run_due(sched, db, now=10001.0)
    assert outcome == {"ran": 0, "passed": 0, "failed": 0, "errors": [],
                       "exit_code": 0, "checked_at": outcome["checked_at"]}
    assert len(history.list_runs(db)) == 1


def test_force_ignores_due_state(tmp_path):
    suite = _suite(str(tmp_path / "s.json"))
    sched = _schedules(str(tmp_path / "sched.json"), [_entry(suite)])
    db = str(tmp_path / "r.db")
    run_due(sched, db, now=10000.0)
    outcome = run_due(sched, db, now=10001.0, force=True)
    assert outcome["ran"] == 1
    assert len(history.list_runs(db)) == 2  # append-only: new row


def test_gate_fail_exit_code(tmp_path):
    suite = _suite(str(tmp_path / "s.json"))
    sched = _schedules(str(tmp_path / "sched.json"),
                       [_entry(suite, candidate="mock:regress", fail_under=0.5)])
    outcome = run_due(sched, str(tmp_path / "r.db"), now=10000.0)
    assert outcome["exit_code"] == 2
    assert outcome["failed"] == 1


def test_refusals_record_no_row_and_last_run_frozen(tmp_path):
    pending = str(tmp_path / "s.pending.json")
    _suite(pending)
    unapproved = _suite(str(tmp_path / "u.json"), approved=False)
    sched = _schedules(str(tmp_path / "sched.json"),
                       [_entry(pending), _entry(unapproved),
                        _entry(unapproved, judge="telepathy")])
    db = str(tmp_path / "r.db")
    outcome = run_due(sched, db, now=10000.0)
    assert outcome["exit_code"] == 1
    assert len(outcome["errors"]) == 3
    assert history.list_runs(db) == []
    with open(sched, encoding="utf-8") as fh:
        assert all("last_run" not in e for e in json.load(fh)["schedules"])


def test_overlapping_ticks_single_flight(tmp_path):
    suite = _suite(str(tmp_path / "s.json"))
    sched = _schedules(str(tmp_path / "sched.json"), [_entry(suite)])
    db = str(tmp_path / "r.db")
    assert history.claim(db, suite, "mock:parity", "mock:parity", now=10000.0)
    outcome = run_due(sched, db, now=10001.0)  # claim held → skipped silently
    assert outcome["ran"] == 0
    assert outcome["exit_code"] == 0


def test_provider_exception_records_failure_row(tmp_path):
    suite = _suite(str(tmp_path / "s.json"))
    sched = _schedules(str(tmp_path / "sched.json"),
                       [_entry(suite, candidate="openai-compat:http://127.0.0.1:9|x")])
    db = str(tmp_path / "r.db")
    outcome = run_due(sched, db, now=10000.0)
    assert outcome["exit_code"] == 1
    rows = history.list_runs(db)
    assert len(rows) == 1
    assert rows[0]["receipt"] is None
    assert rows[0]["error"]
    with open(sched, encoding="utf-8") as fh:
        assert "last_run" not in json.load(fh)["schedules"][0]


def test_threads_overlap_executes_once(tmp_path):
    suite = _suite(str(tmp_path / "s.json"))
    sched = _schedules(str(tmp_path / "sched.json"), [_entry(suite)])
    db = str(tmp_path / "r.db")
    results = []
    barrier = threading.Barrier(2)

    def tick():
        barrier.wait()
        results.append(run_due(sched, db, now=10000.0))

    workers = [threading.Thread(target=tick) for _ in range(2)]
    [w.start() for w in workers]
    [w.join() for w in workers]
    assert sum(r["ran"] for r in results) == 1
    assert len(history.list_runs(db)) == 1


def test_receipt_identical_to_cli_modulo_volatile(tmp_path):
    from test_golden import VOLATILE

    suite = _suite(str(tmp_path / "s.json"))
    sched = _schedules(str(tmp_path / "sched.json"), [_entry(suite)])
    db = str(tmp_path / "r.db")
    run_due(sched, db, now=10000.0)
    stored = history.list_runs(db)[0]["receipt"]
    receipt = str(tmp_path / "cli.json")
    code = main(["compare", "--suite", suite, "--baseline", "mock:parity",
                 "--candidate", "mock:parity", "--out", receipt])
    assert code == EXIT_OK
    with open(receipt, encoding="utf-8") as fh:
        cli_receipt = json.load(fh)
    strip = lambda r: {k: v for k, v in r.items() if k not in VOLATILE}  # noqa: E731
    assert strip(stored) == strip(cli_receipt)


def test_cli_exit_codes(tmp_path):
    suite = _suite(str(tmp_path / "s.json"))
    sched = str(tmp_path / "sched.json")
    db = str(tmp_path / "r.db")

    _schedules(sched, [_entry(suite)])
    assert main(["run-scheduled", "--schedules", sched, "--history", db,
                 "--force"]) == EXIT_OK

    _schedules(sched, [_entry(suite, candidate="mock:regress", fail_under=0.5)])
    assert main(["run-scheduled", "--schedules", sched, "--history", db,
                 "--force"]) == EXIT_GATE_FAIL

    _schedules(sched, [_entry(suite, judge="telepathy")])
    assert main(["run-scheduled", "--schedules", sched, "--history", db,
                 "--force"]) == EXIT_ERROR

    assert main(["run-scheduled", "--schedules", str(tmp_path / "nope.json"),
                 "--history", db]) == EXIT_ERROR
