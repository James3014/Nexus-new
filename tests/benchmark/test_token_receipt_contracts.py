from scripts.bench.receipt_contracts import (
    build_row_receipt_fields,
    expected_capability_invocation_coverage,
    receipt_data_contract,
)
from scripts.bench.token_contracts import token_data_contract


def test_receipt_contract_blocks_missing_with_nexus_capability_receipts():
    contract = receipt_data_contract(
        {
            "mode": "with_nexus",
            "expected_capability_receipt_coverage": {"missing": ["swarm", ""]},
        }
    )

    assert contract == {
        "status": "DATA_CONTRACT_VIOLATION",
        "missing": ["swarm"],
        "reason": "missing_expected_capability_receipts",
    }


def test_receipt_contract_is_not_applicable_for_direct_arm():
    assert receipt_data_contract({"mode": "without_nexus"}) == {
        "status": "NOT_APPLICABLE",
        "missing": [],
        "reason": "non_nexus_arm",
    }


def test_expected_capability_invocation_coverage_requires_selected_invoked_evidence():
    coverage = expected_capability_invocation_coverage(
        ("autoreason", "swarm", "ddtree"),
        [
            {"name": "autoreason", "selected": True, "invoked": True, "evidence_present": True},
            {"name": "swarm", "selected": True, "invoked": False, "evidence_present": True},
        ],
    )

    assert coverage == {
        "expected": ["autoreason", "swarm", "ddtree"],
        "invoked": ["autoreason"],
        "missing": ["swarm", "ddtree"],
        "failure_reasons": {"swarm": "not_invoked", "ddtree": "missing_receipt"},
        "all_invoked_with_evidence": False,
    }


def test_build_row_receipt_fields_serializes_receipts_and_skill_mount_contracts():
    receipt = {
        "name": "autoreason",
        "selected": True,
        "invoked": True,
        "evidence_present": True,
        "gate_passed": True,
        "outcome_contributed": True,
        "public_claim_safe": True,
    }

    fields = build_row_receipt_fields(
        expected_capabilities=("autoreason",),
        capability_receipts=[receipt],
        skill_mount_contract=[{"capability": "autoreason", "status": "PASS"}],
        skill_mount_contract_status="PASS",
        skill_mount_violations=[],
    )

    assert fields["capability_receipts"] == [receipt]
    assert fields["expected_capability_receipt_coverage"]["missing"] == []
    assert fields["expected_capability_invocation_coverage"]["missing"] == []
    assert fields["skill_mount_count"] == 1
    assert fields["skill_mount_contract_status"] == "PASS"
    assert '"autoreason"' in fields["capability_receipts_json"]


def test_token_contract_blocks_model_call_without_measured_provider_tokens():
    contract = token_data_contract(
        {
            "model_calls": 1,
            "total_tokens": 0,
            "token_capture_status": "missing",
            "gateway_token_source": "",
        }
    )

    assert contract == {
        "status": "DATA_CONTRACT_VIOLATION",
        "reason": "model_call_without_measured_provider_tokens",
        "source": "missing",
    }


def test_token_contract_marks_no_model_rows_not_applicable():
    assert token_data_contract({"model_calls": 0, "total_tokens": 0}) == {
        "status": "NOT_APPLICABLE",
        "reason": "no_model_call",
        "source": "none",
    }
