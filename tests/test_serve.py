"""P4: hosted API route tests (live localhost server, ephemeral port)."""

import json
import sqlite3
import threading
import urllib.error
import urllib.request

import pytest

from swapgate import history, teams as teams_mod
from swapgate.cli import EXIT_ERROR, main
from swapgate.serve import create_server

SERVER_KEY = b"test-server-key-32bytes-padding!"


def _suite(approved=True):
    return {"name": "web", "version": "0.1.0",
            "cases": [{"id": "w1",
                       "input": [{"role": "user", "content": "Summarise the refund policy"}],
                       "rubric": [{"type": "contains", "values": ["refund", "policy"]}],
                       "expected": "", "tags": [], "source_trace_ids": []}],
            "metadata": {"approved": {"by": "human", "at": "t"}} if approved else {}}


@pytest.fixture()
def hosted(tmp_path):
    db = str(tmp_path / "r.db")
    team = teams_mod.create_team(db, "a")
    key = teams_mod.issue_key(db, team)
    other = teams_mod.create_team(db, "b")
    other_key = teams_mod.issue_key(db, other)
    server = create_server(0, db, SERVER_KEY)
    port = server.server_address[1]
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    yield {"port": port, "db": db, "key": key, "other_key": other_key}
    server.shutdown()
    server.server_close()
    worker.join(timeout=5)


def _call(port, method, path, body=None, key="", raw=None, headers=None):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, method=method)
    if key:
        req.add_header("Authorization", f"Bearer {key}")
    for name, value in (headers or {}).items():
        req.add_header(name, value)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())


def test_compare_happy_path(hosted):
    status, payload = _call(hosted["port"], "POST", "/v1/compare",
                            {"suite": _suite(), "baseline": "mock:parity",
                             "candidate": "mock:parity"},
                            key=hosted["key"])
    assert status == 200
    assert payload["receipt"]["summary"]["passed"] is True
    assert payload["receipt"]["signature_scheme"] == "hmac-sha256-v1"
    from swapgate.receipt import verify_receipt
    assert verify_receipt(payload["receipt"], SERVER_KEY)
    rows = history.list_runs(hosted["db"])
    assert len(rows) == 1 and rows[0]["team_id"] is not None


def test_compare_rejects(hosted):
    port, key = hosted["port"], hosted["key"]
    cases = [
        ({"suite": _suite(approved=False)}, 400),           # unapproved
        ({"suite": _suite(), "judge": "telepathy"}, 400),   # bad judge
        ({"suite": _suite(), "fail_under": "high"}, 400),   # bad threshold type
        ({"suite": _suite(), "fail_under": True}, 400),     # bool rejected
        ({"suite": _suite(), "max_regression": 1.5}, 400),  # out of range
        ({"suite": _suite(), "baseline": "nope:x"}, 400),   # bad provider
        ({"nonsense": 1}, 400),                             # no suite
    ]
    for body, expected in cases:
        status, payload = _call(port, "POST", "/v1/compare", body, key=key)
        assert status == expected, (body, status, payload)
        assert "error" in payload
    assert history.list_runs(hosted["db"]) == []  # nothing recorded


def test_compare_rejects_nonfinite_and_malformed(hosted):
    port, key = hosted["port"], hosted["key"]
    status, _ = _call(port, "POST", "/v1/compare",
                      raw=b'{"suite": {}, "fail_under": Infinity}', key=key)
    assert status == 400
    status, _ = _call(port, "POST", "/v1/compare", raw=b"{oops", key=key)
    assert status == 400
    status, _ = _call(port, "POST", "/v1/compare", raw=b"x" * (1024 * 1024 + 1), key=key)
    assert status == 413


def test_auth_required(hosted):
    port = hosted["port"]
    status, _ = _call(port, "POST", "/v1/compare", {"suite": _suite()})
    assert status == 401
    status, _ = _call(port, "POST", "/v1/compare", {"suite": _suite()}, key="bogus")
    assert status == 401
    status, _ = _call(port, "GET", "/v1/runs")
    assert status == 401
    status, _ = _call(port, "GET", "/nope", key=hosted["key"])
    assert status == 404


def test_team_scoping_and_null_invisible(hosted):
    port, key, db = hosted["port"], hosted["key"], hosted["db"]
    _call(port, "POST", "/v1/compare", {"suite": _suite()}, key=key)
    _call(port, "POST", "/v1/compare", {"suite": _suite()}, key=hosted["other_key"])
    history.append_run(db, {"suite": "local", "baseline": "b", "candidate": "c",
                              "judge": "d", "fail_under": 0.0, "max_regression": 1.0,
                              "passed": True, "receipt": {"summary": {}}, "error": None,
                              "team_id": None})
    status, payload = _call(port, "GET", "/v1/runs", key=key)
    assert status == 200
    assert len(payload["runs"]) == 1
    own_id = payload["runs"][0]["id"]
    status, payload = _call(port, "GET", f"/v1/runs/{own_id}", key=key)
    assert status == 200
    others = [r for r in history.list_runs(db) if r["team_id"] is not None
              and r["id"] != own_id]
    assert others
    status, _ = _call(port, "GET", f"/v1/runs/{others[0]['id']}", key=key)
    assert status == 404  # foreign → 404, not 403
    nulls = [r for r in history.list_runs(db) if r["team_id"] is None]
    status, _ = _call(port, "GET", f"/v1/runs/{nulls[0]['id']}", key=key)
    assert status == 404  # NULL-team never served
    status, payload = _call(port, "GET", f"/v1/receipts/{own_id}", key=key)
    assert status == 200 and payload["receipt"]["summary"]["passed"] is True


def test_provider_error_row_and_receipt_404(hosted):
    port, key = hosted["port"], hosted["key"]
    status, payload = _call(port, "POST", "/v1/compare",
                            {"suite": _suite(),
                             "candidate": "openai-compat:http://127.0.0.1:9|x"},
                            key=key)
    assert status == 500
    rows = history.list_runs(hosted["db"])
    assert len(rows) == 1 and rows[0]["receipt"] is None
    status, _ = _call(port, "GET", f"/v1/receipts/{rows[0]['id']}", key=key)
    assert status == 404


def test_cli_teams_create_and_serve_bind_conflict(tmp_path, capsys):
    db = str(tmp_path / "r.db")
    assert main(["teams", "create", "cli-team", "--history", db]) == 0
    out = capsys.readouterr().out.strip()
    assert len(out) > 20
    assert main(["teams", "create", "cli-team", "--history", db]) == EXIT_ERROR
    server = create_server(0, db, SERVER_KEY)
    port = server.server_address[1]
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        code = main(["serve", "--port", str(port), "--history", db,
                     "--key", str(tmp_path / "k")])
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)
    assert code == EXIT_ERROR


def test_schema_v2_migrates_v1_db(tmp_path):
    db = str(tmp_path / "r.db")
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE schema_version (version INTEGER PRIMARY KEY)")
    conn.execute("INSERT INTO schema_version VALUES (1)")
    conn.execute("CREATE TABLE runs (id INTEGER PRIMARY KEY, ts REAL, suite TEXT)")
    conn.commit()
    conn.close()
    assert history.init_db(db) == 2
    conn = sqlite3.connect(db)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(runs)").fetchall()]
    conn.close()
    assert "team_id" in cols
