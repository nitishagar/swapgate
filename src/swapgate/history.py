"""Append-only run history (stdlib sqlite3).

Connection discipline: short-lived per-operation connections (never shared
across threads — `check_same_thread` stays True), WAL mode, 5s busy timeout,
rollback-on-exception. Schema evolves through additive migrations only.
"""

from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from typing import Any, Iterator

BUSY_TIMEOUT_MS = 5000
CLAIM_TTL_S = 3600

_MIGRATIONS = {
    1: [
        "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY)",
        """CREATE TABLE IF NOT EXISTS runs (
             id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL,
             suite TEXT NOT NULL, baseline TEXT NOT NULL, candidate TEXT NOT NULL,
             judge TEXT NOT NULL, fail_under REAL NOT NULL, max_regression REAL NOT NULL,
             passed INTEGER, baseline_pass_rate REAL, candidate_pass_rate REAL,
             receipt TEXT, error TEXT)""",
        """CREATE TABLE IF NOT EXISTS claims (
             suite_path TEXT NOT NULL, baseline TEXT NOT NULL, candidate TEXT NOT NULL,
             claimed_at REAL NOT NULL, pid INTEGER NOT NULL,
             PRIMARY KEY (suite_path, baseline, candidate))""",
    ],
}


@contextmanager
def _connect(path: str) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(path, timeout=BUSY_TIMEOUT_MS / 1000)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _applied(conn: sqlite3.Connection) -> set[int]:
    try:
        rows = conn.execute("SELECT version FROM schema_version").fetchall()
    except sqlite3.OperationalError:
        return set()
    return {r[0] for r in rows}


def init_db(path: str) -> int:
    """Apply pending migrations; return the schema version."""
    with _connect(path) as conn:
        applied = _applied(conn)
        for version in sorted(_MIGRATIONS):
            if version in applied:
                continue
            for statement in _MIGRATIONS[version]:
                conn.execute(statement)
            conn.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))
            applied.add(version)
    return max(applied)


def append_run(path: str, run: dict[str, Any]) -> int:
    """Append one run row; never mutates existing rows. Returns the row id."""
    init_db(path)
    with _connect(path) as conn:
        cursor = conn.execute(
            """INSERT INTO runs (ts, suite, baseline, candidate, judge, fail_under,
               max_regression, passed, baseline_pass_rate, candidate_pass_rate,
               receipt, error)
               VALUES (:ts, :suite, :baseline, :candidate, :judge, :fail_under,
               :max_regression, :passed, :baseline_pass_rate, :candidate_pass_rate,
               :receipt, :error)""",
            {
                "ts": time.time(),
                "suite": run["suite"],
                "baseline": run["baseline"],
                "candidate": run["candidate"],
                "judge": run["judge"],
                "fail_under": run["fail_under"],
                "max_regression": run["max_regression"],
                "passed": run.get("passed"),
                "baseline_pass_rate": run.get("baseline_pass_rate"),
                "candidate_pass_rate": run.get("candidate_pass_rate"),
                "receipt": json.dumps(run["receipt"], sort_keys=True) if run.get("receipt") else None,
                "error": run.get("error"),
            },
        )
        return int(cursor.lastrowid or 0)


def list_runs(path: str) -> list[dict[str, Any]]:
    """Newest-first run rows (receipts decoded)."""
    init_db(path)
    with _connect(path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM runs ORDER BY id DESC").fetchall()
    out = []
    for row in rows:
        item = dict(row)
        item["receipt"] = json.loads(item["receipt"]) if item["receipt"] else None
        out.append(item)
    return out


def claim(path: str, suite_path: str, baseline: str, candidate: str,
          now: float | None = None, pid: int | None = None) -> bool:
    """Single-flight claim. True if acquired; stale claims (>TTL) are reaped."""
    import os

    init_db(path)
    now = time.time() if now is None else now
    pid = os.getpid() if pid is None else pid
    conn = sqlite3.connect(path, timeout=BUSY_TIMEOUT_MS / 1000)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute("DELETE FROM claims WHERE claimed_at < ?", (now - CLAIM_TTL_S,))
            cursor = conn.execute(
                """INSERT OR IGNORE INTO claims
                   (suite_path, baseline, candidate, claimed_at, pid)
                   VALUES (?, ?, ?, ?, ?)""",
                (suite_path, baseline, candidate, now, pid),
            )
            acquired = cursor.rowcount == 1
            conn.commit()
            return acquired
        except Exception:
            conn.rollback()
            raise
    finally:
        conn.close()


def release(path: str, suite_path: str, baseline: str, candidate: str) -> None:
    with _connect(path) as conn:
        conn.execute(
            "DELETE FROM claims WHERE suite_path=? AND baseline=? AND candidate=?",
            (suite_path, baseline, candidate),
        )
