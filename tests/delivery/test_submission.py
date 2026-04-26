from pathlib import Path

from nexus.delivery.submission import assess_submission
from nexus.delivery.submission import build_submission_payload
from nexus.delivery.submission import governance_payload
from nexus.delivery.submission import load_delivery_receipt


def test_load_delivery_receipt_returns_empty_payload_for_missing_file(tmp_path: Path) -> None:
    payload = load_delivery_receipt(tmp_path / "missing.json")
    assert payload == {}


def test_assess_submission_fails_closed_without_acceptance_gate(tmp_path: Path) -> None:
    assessment = assess_submission(
        receipt_payload={"delivery_gate_passed": True},
        derived_bundle={"claim_state": "VERIFIED", "confidence_level": "HIGH"},
        receipt_path=tmp_path / "delivery_gate.json",
    )

    assert assessment.delivery_gate_passed is True
    assert assessment.acceptance_gate_passed is False
    assert assessment.passed is False
    assert assessment.phantom_blocked is True
    assert assessment.gate_summary["acceptance_check"] == "FAIL"


def test_assess_submission_reports_pass_only_when_all_receipts_and_claims_align(tmp_path: Path) -> None:
    assessment = assess_submission(
        receipt_payload={
            "delivery_gate_passed": True,
            "acceptance_result": {"gate_passed": True},
        },
        derived_bundle={"claim_state": "VERIFIED", "confidence_level": "HIGH"},
        receipt_path=tmp_path / "delivery_gate.json",
    )

    payload = build_submission_payload(commit_sha="abc123", assessment=assessment)

    assert assessment.passed is True
    assert governance_payload("T1", assessment) == {
        "task_id": "T1",
        "pass": True,
        "phantom_blocked": False,
        "proof_present": True,
    }
    assert payload["commit_sha"] == "abc123"
    assert payload["gate_summary"]["delivery_gate"] == "PASS"
    assert payload["gate_summary"]["acceptance_check"] == "PASS"
