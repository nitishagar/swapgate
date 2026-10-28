"""Decision receipts: tamper-evident, signed swap verdicts.

Canonical JSON (sorted keys, compact separators) is hashed with sha256 and
signed with HMAC-SHA256 under a local key file. Offline by design; the
documented upgrade path is Ed25519 signatures for third-party verification.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from typing import Any

RECEIPT_VERSION = 1
DEFAULT_KEY_PATH = os.path.expanduser("~/.swapgate/key")


def _normalize(value: Any) -> Any:
    """Shortest round-trip numbers (1.0 -> 1), matching JSON.stringify."""
    if isinstance(value, bool):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, dict):
        return {k: _normalize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalize(v) for v in value]
    return value


def canonical(payload: dict[str, Any]) -> bytes:
    return json.dumps(_normalize(payload), ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode()


def content_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical(payload)).hexdigest()


def load_or_create_key(path: str = DEFAULT_KEY_PATH) -> bytes:
    if os.path.exists(path):
        with open(path, "rb") as fh:
            return fh.read().strip()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    key = os.urandom(32)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(key.hex().encode())
    return key.hex().encode()


def build_receipt_body(summary: dict[str, Any], cases: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "v": RECEIPT_VERSION,
        "issued_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "cases": cases,
    }


def sign_receipt(body: dict[str, Any], key: bytes) -> dict[str, Any]:
    digest = content_hash(body)
    sig = hmac.new(key, digest.encode(), hashlib.sha256).hexdigest()
    return {**body, "content_hash": digest, "signature": sig, "signature_scheme": "hmac-sha256-v1"}


def verify_receipt(receipt: dict[str, Any], key: bytes) -> bool:
    body = {k: v for k, v in receipt.items() if k not in ("content_hash", "signature", "signature_scheme")}
    if receipt.get("signature_scheme") != "hmac-sha256-v1":
        return False
    if content_hash(body) != receipt.get("content_hash"):
        return False
    expected = hmac.new(key, str(receipt["content_hash"]).encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, str(receipt.get("signature", "")))


def save_receipt(receipt: dict[str, Any], path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(receipt, fh, ensure_ascii=False, indent=2, sort_keys=True)


def load_receipt(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)
