"""Bharat pack v0: Hinglish eval templates, DPDP profiles, FREE-AI report mapping.

- Hinglish/Indic support prompt templates for building locale suites.
- DPDP-aware redaction: the `bharat` and `dpdp-strict` profiles in redact.py
  (PAN, Aadhaar, UPI ids, +91 phones) plus a 30-day retention recommendation.
- FREE-AI mapping: receipt summary fields mapped onto the RBI FREE-AI
  governance/assurance language for fintech audit packets.
"""

from __future__ import annotations

from typing import Any

HINGLISH_TEMPLATES = [
    "Mera claim reject ho gaya hai, mujhe appeal draft karne mein help karo. Policy: {policy}.",
    "Mere GST notice ka jawab likho. Notice number {notice_no} hai.",
    "Main kaun si sarkari yojana ke liye eligible hoon? Meri umar {age} hai.",
    "My UPI AutoPay of Rs {amount} failed twice. Draft a complaint to the bank.",
    "Summarise this insurance clause in simple Hindi: {clause}.",
]

DPDP_RETENTION_DAYS = 30
DPDP_NOTE = (
    "DPDP Act 2023: traces are personal data. Minimise collection, pseudonymise "
    "before storage (redact profile 'bharat' or 'dpdp-strict'), retain at most "
    f"{DPDP_RETENTION_DAYS} days, delete on request. Full duties from 13 May 2027."
)

# Receipt summary keys -> (FREE-AI pillar, control description)
FREE_AI_MAPPING = {
    "suite": ("Governance", "Named eval suite under version control"),
    "baseline": ("Assurance", "Reference model behaviour recorded"),
    "candidate": ("Assurance", "Candidate model behaviour under test"),
    "candidate_pass_rate": ("Assurance", "Quantified capability measure"),
    "regression_gap": ("Governance", "Change-control gate metric"),
    "passed": ("Governance", "Recorded go/no-go decision"),
    "content_hash": ("Assurance", "Tamper-evident evidence binding"),
}


def apply_pack(suite: Any) -> Any:
    """Tag every case with the Bharat pack marker (idempotent)."""
    for case in suite.cases:
        if "pack:bharat-v0" not in case.tags:
            case.tags.append("pack:bharat-v0")
    suite.metadata["pack"] = "bharat-v0"
    suite.metadata["dpdp_note"] = DPDP_NOTE
    return suite


def free_ai_annex(receipt: dict[str, Any]) -> list[dict[str, str]]:
    """Build a FREE-AI control annex from a signed receipt."""
    summary = receipt.get("summary", {})
    annex = []
    for key, (pillar, control) in FREE_AI_MAPPING.items():
        value = summary.get(key, receipt.get(key, ""))
        annex.append({
            "pillar": pillar,
            "control": control,
            "field": key,
            "value": str(value),
        })
    return annex
