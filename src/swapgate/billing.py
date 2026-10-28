"""Test-mode billing webhooks (real provider SDKs, imported lazily).

`billing` module import never touches the SDKs; each verifier imports inside
the function so base installs work and the diet guard can prove it. Webhooks
are record-only: beyond the ledger row there are no side effects, which makes
crash-retry reprocessing naturally idempotent.
"""

from __future__ import annotations

import time

from .history import _connect, init_db

LIVE_PATTERNS = ("sk_live_", "rzp_live_")
STRIPE_TOLERANCE_S = 300


def check_test_mode(config: dict[str, str]) -> None:
    """Refuse live-shaped credentials anywhere in billing config."""
    for name, value in config.items():
        if value and any(pat in value for pat in LIVE_PATTERNS):
            raise ValueError(f"live credentials rejected for {name} (test-mode only)")


def verify_stripe(payload: bytes, sig_header: str, secret: str) -> dict:
    """Verify a Stripe webhook; returns the event dict. Raises on failure."""
    import stripe

    return stripe.Webhook.construct_event(
        payload, sig_header, secret, tolerance=STRIPE_TOLERANCE_S)


def verify_razorpay(raw_text: str, signature: str, secret: str) -> None:
    """Verify a Razorpay webhook over the RAW request text. Raises on failure."""
    from razorpay import Client

    Client(auth=("unused", "unused")).utility.verify_webhook_signature(
        raw_text, signature, secret)


def record_event(db_path: str, provider: str, event_key: str,
                 payload: str | None) -> bool:
    """Insert-first event ledger. True if newly processed, False if duplicate."""
    init_db(db_path)
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT status FROM webhook_events WHERE provider=? AND event_key=?",
            (provider, event_key)).fetchone()
        if row is not None and row[0] == "processed":
            return False
        conn.execute(
            """INSERT OR IGNORE INTO webhook_events
               (provider, event_key, status, received_at, payload)
               VALUES (?, ?, 'received', ?, ?)""",
            (provider, event_key, time.time(), payload),
        )
        conn.execute(
            "UPDATE webhook_events SET status='processed' WHERE provider=? AND event_key=?",
            (provider, event_key),
        )
        return True
