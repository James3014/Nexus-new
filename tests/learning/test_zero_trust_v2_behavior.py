from __future__ import annotations

from nexus.learning.zero_trust_v2_behavior import extract_behavior_receipt_from_bundle


def test_extract_behavior_receipt_requires_all_fields() -> None:
    result = extract_behavior_receipt_from_bundle(
        {
            "receipt": {
                "selected": True,
                "evidence_present": True,
                "outcome_contributed": True,
                "trust_mismatch": False,
            }
        }
    )

    assert result["status"] == "BLOCKED"
    assert "MISSING_BEHAVIOR_FIELD:injected" in result["failed_security_contract_rules"]
    assert "MISSING_BEHAVIOR_FIELD:used" in result["failed_security_contract_rules"]
    assert "MISSING_BEHAVIOR_FIELD:gate_passed" in result["failed_security_contract_rules"]


def test_extract_behavior_receipt_passes_complete_clean_receipt() -> None:
    result = extract_behavior_receipt_from_bundle(
        {
            "receipt": {
                "selected": True,
                "injected": True,
                "used": True,
                "evidence_present": True,
                "gate_passed": True,
                "outcome_contributed": True,
                "trust_mismatch": False,
            }
        }
    )

    assert result["status"] == "PASS"
    assert result["failed_security_contract_rules"] == []
