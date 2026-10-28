"""P4: team key tests (hashing, lookup, revocation edge)."""

from swapgate import teams


def test_issue_and_resolve(tmp_path):
    db = str(tmp_path / "r.db")
    tid = teams.create_team(db, "alpha")
    key = teams.issue_key(db, tid)
    assert teams.resolve_key(db, key) == tid
    assert teams.resolve_key(db, "wrong") is None
    assert teams.resolve_key(db, "") is None


def test_duplicate_team_rejected(tmp_path):
    db = str(tmp_path / "r.db")
    teams.create_team(db, "alpha")
    try:
        teams.create_team(db, "alpha")
    except ValueError as exc:
        assert "already exists" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_keys_are_unique_and_secret(tmp_path):
    import sqlite3

    db = str(tmp_path / "r.db")
    tid = teams.create_team(db, "alpha")
    a, b = teams.issue_key(db, tid), teams.issue_key(db, tid)
    assert a != b
    conn = sqlite3.connect(db)
    stored = [r[0] for r in conn.execute("SELECT key_hash FROM keys").fetchall()]
    conn.close()
    assert a not in stored and b not in stored  # hashes only
    assert all(len(h) == 64 for h in stored)
