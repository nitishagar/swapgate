"""P4: billing webhook tests (real SDKs, local HMAC — no network)."""

import hashlib
import hmac
import json
import sqlite3
import threading
import time
import urllib.error
import urllib.request

import pytest

pytest.importorskip("stripe")
pytest.importorskip("razorpay")

import stripe  # noqa: E402
from stripe import WebhookSignature  # noqa: E402

from swapgate.serve import create_server  # noqa: E402

STRIPE_SECRET = "whsec_testbilling1"
RAZORPAY_SECRET = "rzpay_testsecret1"


@pytest.fixture()
def billed(tmp_path, monkeypatch):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", STRIPE_SECRET)
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", RAZORPAY_SECRET)
    monkeypatch.setenv("RAZORPAY_TEST_ACCOUNTS", "acc_test1")
    db = str(tmp_path / "r.db")
    server = create_server(0, db, b"test-server-key-32bytes-padding!")
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    yield {"port": server.server_address[1], "db": db}
    server.shutdown()
    server.server_close()
    worker.join(timeout=5)


def _post(port, path, raw, headers):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=raw, method="POST")
    for name, value in headers.items():
        req.add_header(name, value)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())


def _stripe_post(port, event_id, livemode=False, secret=STRIPE_SECRET):
    payload = json.dumps({"id": event_id, "type": "test.event",
                          "livemode": livemode}).encode()
    ts = int(time.time())
    sig = WebhookSignature._compute_signature(f"{ts}." + payload.decode(), secret)
    return _post(port, "/v1/billing/stripe/webhook", payload,
                 {"Stripe-Signature": f"t={ts},v1={sig}"})


def _razorpay_post(port, event_id, account="acc_test1", secret=RAZORPAY_SECRET, event="payment.captured"):
    body = {"event": event, "account_id": account,
            "payload": {"payment": {"entity": {"id": event_id}}}}
    raw = json.dumps(body).encode()
    sig = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return _post(port, "/v1/billing/razorpay/webhook", raw,
                 {"X-Razorpay-Signature": sig})


def _ledger(db):
    conn = sqlite3.connect(db)
    rows = conn.execute("SELECT provider, event_key, status FROM webhook_events").fetchall()
    conn.close()
    return rows


def test_stripe_accept_and_duplicate(billed):
    port, db = billed["port"], billed["db"]
    assert _stripe_post(port, "evt_a1")[0] == 200
    assert _stripe_post(port, "evt_a1")[0] == 200  # duplicate → 200 no-op
    assert _ledger(db) == [("stripe", "evt_a1", "processed")]


def test_stripe_rejects(billed):
    port, db = billed["port"], billed["db"]
    assert _stripe_post(port, "evt_bad", secret="whsec_wrong")[0] == 400
    assert _stripe_post(port, "evt_live", livemode=True)[0] == 400
    assert _ledger(db) == []


def test_razorpay_accept_and_duplicate(billed):
    port, db = billed["port"], billed["db"]
    assert _razorpay_post(port, "pay_b1")[0] == 200
    assert _razorpay_post(port, "pay_b1")[0] == 200
    assert _ledger(db) == [("razorpay", "payment.captured:pay_b1", "processed")]


def test_razorpay_rejects(billed):
    port, db = billed["port"], billed["db"]
    assert _razorpay_post(port, "pay_x", secret="wrong")[0] == 400
    assert _razorpay_post(port, "pay_y", account="acc_live")[0] == 400
    assert _ledger(db) == []


def test_unconfigured_provider_500s(tmp_path, monkeypatch):
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("RAZORPAY_WEBHOOK_SECRET", raising=False)
    db = str(tmp_path / "r.db")
    server = create_server(0, db, b"test-server-key-32bytes-padding!")
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        status, payload = _post(server.server_address[1], "/v1/billing/stripe/webhook",
                                b"{}", {"Stripe-Signature": "t=1,v1=x"})
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)
    assert status == 500
    assert payload["error"]["code"] == "billing_unconfigured"


def test_live_shaped_secret_refused(tmp_path, monkeypatch):
    from swapgate import billing

    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_ok")
    try:
        billing.check_test_mode({"X": "sk_live_abc123"})
    except ValueError as exc:
        assert "test-mode only" in str(exc)
    else:
        raise AssertionError("expected ValueError")
    billing.check_test_mode({"X": "whsec_ok", "Y": "rzp_test_id"})
