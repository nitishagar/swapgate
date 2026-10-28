"""G0: Bharat pack tests."""

from swapgate.evals import EvalCase, EvalSuite
from swapgate.bharat import (
    DPDP_NOTE,
    HINGLISH_TEMPLATES,
    apply_pack,
    free_ai_annex,
)
from swapgate.receipt import build_receipt_body, sign_receipt


def test_hinglish_templates_render():
    assert len(HINGLISH_TEMPLATES) >= 5
    rendered = HINGLISH_TEMPLATES[2].format(age=30)
    assert "30" in rendered


def test_apply_pack_tags_and_marks_metadata():
    suite = EvalSuite(name="in", cases=[EvalCase(id="a", input=[])])
    apply_pack(suite)
    assert suite.cases[0].tags == ["pack:bharat-v0"]
    assert suite.metadata["pack"] == "bharat-v0"
    assert "13 May 2027" in suite.metadata["dpdp_note"]
    apply_pack(suite)  # idempotent
    assert suite.cases[0].tags == ["pack:bharat-v0"]


def test_dpdp_note_mentions_controls():
    assert "pseudonymise" in DPDP_NOTE and "30" in DPDP_NOTE


def test_free_ai_annex_covers_governance_and_assurance():
    receipt = sign_receipt(build_receipt_body(
        {"suite": "s", "baseline": "b", "candidate": "c",
         "candidate_pass_rate": 0.9, "regression_gap": 0.0, "passed": True}, []), b"k")
    annex = free_ai_annex(receipt)
    pillars = {row["pillar"] for row in annex}
    assert pillars == {"Governance", "Assurance"}
    by_field = {row["field"]: row for row in annex}
    assert by_field["passed"]["value"] == "True"
    assert by_field["content_hash"]["value"] == receipt["content_hash"]
