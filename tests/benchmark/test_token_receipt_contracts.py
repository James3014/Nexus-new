from scripts.bench.receipt_contracts import receipt_data_contract
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
