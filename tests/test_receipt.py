"""G4: receipt integrity tests."""

import json
import os

from swapgate.receipt import (
    build_receipt_body,
    content_hash,
    load_or_create_key,
    sign_receipt,
    verify_receipt,
)

BODY = {"summary": {"passed": True}, "cases": []}
KEY = b"test-key-abc"


def test_sign_verify_roundtrip():
    body = build_receipt_body({"passed": True}, [])
    receipt = sign_receipt(body, KEY)
    assert verify_receipt(receipt, KEY)


def test_tampered_summary_rejected():
    receipt = sign_receipt(build_receipt_body({"passed": True}, []), KEY)
    receipt["summary"]["passed"] = False
    assert not verify_receipt(receipt, KEY)


def test_tampered_case_rejected():
    receipt = sign_receipt(build_receipt_body({"passed": True}, [{"case_id": "a"}]), KEY)
    receipt["cases"].append({"case_id": "forged"})
    assert not verify_receipt(receipt, KEY)


def test_wrong_key_rejected():
    receipt = sign_receipt(build_receipt_body({"passed": True}, []), KEY)
    assert not verify_receipt(receipt, b"wrong-key")


def test_missing_signature_rejected():
    receipt = sign_receipt(build_receipt_body({"passed": True}, []), KEY)
    del receipt["signature"]
    assert not verify_receipt(receipt, KEY)


def test_wrong_scheme_rejected():
    receipt = sign_receipt(build_receipt_body({"passed": True}, []), KEY)
    receipt["signature_scheme"] = "none"
    assert not verify_receipt(receipt, KEY)


def test_content_hash_stable():
    assert content_hash(BODY) == content_hash(dict(BODY))


def test_checked_in_signed_receipt_verifies():
    """Cross-language anchor: the TS SDK verifies this same file."""
    path = os.path.join(os.path.dirname(__file__), "golden", "signed-receipt.json")
    with open(path, encoding="utf-8") as fh:
        receipt = json.load(fh)
    assert verify_receipt(receipt, b"swapgate-interop-test-key")


def test_key_file_created_with_owner_only_perms(tmp_path):
    path = str(tmp_path / "sub" / "key")
    key = load_or_create_key(path)
    assert os.path.exists(path)
    assert oct(os.stat(path).st_mode & 0o777) == "0o600"
    assert load_or_create_key(path) == key
