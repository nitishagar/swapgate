"""P3: run-history store tests."""

import sqlite3

from swapgate.history import append_run, claim, init_db, list_runs, release


def _run(**over):
    base = {"suite": "s.json", "baseline": "mock:parity", "candidate": "mock:parity",
            "judge": "deterministic", "fail_under": 0.0, "max_regression": 1.0,
            "passed": True, "baseline_pass_rate": 1.0, "candidate_pass_rate": 1.0,
            "receipt": {"summary": {"passed": True}}, "error": None}
    base.update(over)
    return base


def test_init_idempotent_and_versioned(tmp_path):
    db = str(tmp_path / "r.db")
    assert init_db(db) == 2  # migrations 1 (runs/claims) + 2 (teams/keys/webhooks)
    assert init_db(db) == 2
    conn = sqlite3.connect(db)
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    conn.close()
    assert mode.lower() == "wal"


def test_append_and_list_newest_first(tmp_path):
    db = str(tmp_path / "r.db")
    append_run(db, _run(passed=True))
    append_run(db, _run(passed=False))
    rows = list_runs(db)
    assert [r["passed"] for r in rows] == [0, 1]
    assert rows[0]["receipt"] == {"summary": {"passed": True}}
    assert rows[0]["id"] > rows[1]["id"]


def test_failure_row_has_null_receipt(tmp_path):
    db = str(tmp_path / "r.db")
    append_run(db, _run(receipt=None, error="URLError: refused", passed=None))
    rows = list_runs(db)
    assert rows[0]["receipt"] is None
    assert "refused" in rows[0]["error"]


def test_claim_single_flight_and_release(tmp_path):
    db = str(tmp_path / "r.db")
    assert claim(db, "s.json", "mock:parity", "mock:parity")
    assert not claim(db, "s.json", "mock:parity", "mock:parity")
    assert claim(db, "s.json", "mock:parity", "mock:seed-1")  # composite key
    release(db, "s.json", "mock:parity", "mock:parity")
    assert claim(db, "s.json", "mock:parity", "mock:parity")


def test_stale_claim_reaped(tmp_path):
    db = str(tmp_path / "r.db")
    assert claim(db, "s.json", "a", "b", now=1000.0)
    assert not claim(db, "s.json", "a", "b", now=1000.0 + 10)
    assert claim(db, "s.json", "a", "b", now=1000.0 + 7200)  # past 1h TTL
