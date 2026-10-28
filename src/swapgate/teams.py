"""Team API keys (sha256-hashed, constant-time lookup)."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
import time

from .history import _connect, init_db


def _hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def create_team(db_path: str, name: str) -> int:
    """Create a team; raises ValueError if the name exists."""
    init_db(db_path)
    with _connect(db_path) as conn:
        try:
            cursor = conn.execute(
                "INSERT INTO teams (name, created) VALUES (?, ?)", (name, time.time()))
        except sqlite3.IntegrityError:
            raise ValueError(f"team already exists: {name}")
        return int(cursor.lastrowid or 0)


def issue_key(db_path: str, team_id: int) -> str:
    """Mint a key; the plaintext is returned once and never stored."""
    init_db(db_path)
    key = secrets.token_urlsafe(32)
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT INTO keys (key_hash, team_id, created, revoked) VALUES (?, ?, ?, 0)",
            (_hash_key(key), team_id, time.time()),
        )
    return key


def resolve_key(db_path: str, key: str) -> int | None:
    """Return the team id for a valid, unrevoked key; else None."""
    init_db(db_path)
    want = _hash_key(key)
    with _connect(db_path) as conn:
        rows = conn.execute("SELECT key_hash, team_id FROM keys WHERE revoked = 0").fetchall()
    for key_hash, team_id in rows:
        if hmac.compare_digest(key_hash, want):
            return int(team_id)
    return None
