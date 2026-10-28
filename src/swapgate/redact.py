"""PII pseudonymiser (lexvault-style): deterministic, profile-driven, offline.

Patterns are replaced with stable pseudonyms (`<EMAIL_a1b2c3>`) derived from
HMAC-SHA256 over (key, label, value), so clustering and evals stay stable
while raw PII never lands in stored traces.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from dataclasses import dataclass

from .traces import TraceEvent

DEFAULT_KEY = b"swapgate-local-pseudonym-key-v1"

_PATTERNS: dict[str, list[str]] = {
    "EMAIL": [r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"],
    "PHONE_IN": [r"(?:\+91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}"],
    "PHONE_GENERIC": [r"\+\d{1,3}[\s-]?\d{3,}[\s-]?\d{3,}"],
    "PAN": [r"\b[A-Z]{5}[0-9]{4}[A-Z]\b"],
    "AADHAAR": [r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"],
    "UPI": [r"\b[A-Za-z0-9._-]{2,}@[A-Za-z]{2,}\b"],
    "IP": [r"\b(?:\d{1,3}\.){3}\d{1,3}\b"],
    "API_KEY": [r"\b(?:sk-|xox[bap]-|ghp_|gho_)[A-Za-z0-9_-]{8,}\b"],
}

PROFILES: dict[str, list[str]] = {
    "default": ["EMAIL", "PHONE_GENERIC", "API_KEY", "IP"],
    "bharat": ["EMAIL", "PHONE_IN", "PAN", "AADHAAR", "UPI", "API_KEY", "IP"],
    "dpdp-strict": ["EMAIL", "PHONE_IN", "PHONE_GENERIC", "PAN", "AADHAAR", "UPI", "API_KEY", "IP"],
}


@dataclass
class Redactor:
    profile: str = "default"
    key: bytes = DEFAULT_KEY

    def __post_init__(self) -> None:
        if self.profile not in PROFILES:
            raise ValueError(f"unknown redact profile: {self.profile}")
        self._compiled = [
            (label, re.compile(pattern))
            for label in PROFILES[self.profile]
            for pattern in _PATTERNS[label]
        ]

    def pseudonym(self, label: str, value: str) -> str:
        digest = hmac.new(self.key, f"{label}:{value}".encode(), hashlib.sha256).hexdigest()
        return f"<{label}_{digest[:6]}>"

    def redact_text(self, text: str) -> str:
        for label, pattern in self._compiled:
            text = pattern.sub(lambda m: self.pseudonym(label, m.group(0)), text)
        return text

    def redact_event(self, event: TraceEvent) -> TraceEvent:
        event.messages = [
            {"role": m.get("role", "user"), "content": self.redact_text(m.get("content", ""))}
            for m in event.messages
        ]
        event.output = self.redact_text(event.output)
        return event
