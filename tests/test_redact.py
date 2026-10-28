"""G0: redaction unit tests."""

import pytest

from swapgate.redact import Redactor
from swapgate.traces import TraceEvent


def test_default_profile_redacts_email_and_key():
    r = Redactor("default")
    out = r.redact_text("mail bob@example.com key sk-abcdef123456 done")
    assert "bob@example.com" not in out
    assert "sk-abcdef123456" not in out
    assert "<EMAIL_" in out and "<API_KEY_" in out
    assert out.endswith("done")


def test_bharat_profile_redacts_pan_upi_phone():
    r = Redactor("bharat")
    out = r.redact_text("PAN ABCDE1234F UPI priya@okhdfc phone +91 98765 43210")
    assert "ABCDE1234F" not in out
    assert "priya@okhdfc" not in out
    assert "98765 43210" not in out
    assert "<PAN_" in out and "<UPI_" in out and "<PHONE_IN_" in out


def test_dpdp_strict_redacts_aadhaar():
    r = Redactor("dpdp-strict")
    out = r.redact_text("Aadhaar 1234 5678 9012")
    assert "1234 5678 9012" not in out
    assert "<AADHAAR_" in out


def test_default_profile_leaves_bharat_ids():
    r = Redactor("default")
    assert "ABCDE1234F" in r.redact_text("PAN ABCDE1234F")


def test_pseudonyms_are_deterministic():
    r = Redactor("bharat")
    assert r.redact_text("a@b.co") == r.redact_text("a@b.co")


def test_pseudonyms_differ_by_key():
    a = Redactor("default", key=b"key-one").redact_text("a@b.co")
    b = Redactor("default", key=b"key-two").redact_text("a@b.co")
    assert a != b


def test_unknown_profile_rejected():
    with pytest.raises(ValueError):
        Redactor("nsa")


def test_redact_event_covers_messages_and_output():
    r = Redactor("default")
    ev = TraceEvent(
        trace_id="t", model="m",
        messages=[{"role": "user", "content": "hi bob@example.com"}],
        output="bye bob@example.com",
    )
    r.redact_event(ev)
    assert "bob@example.com" not in ev.messages[0]["content"]
    assert "bob@example.com" not in ev.output
