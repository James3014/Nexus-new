from scripts.bench.run_contracts import apply_contracts_to_row, build_rubric_contract


def test_apply_contracts_marks_missing_receipt_and_unmeasured_tokens():
    row = {
        "mode": "with_nexus",
        "model_calls": 1,
        "total_tokens": 0,
        "token_capture_status": "missing",
        "gateway_token_source": "missing",
        "expected_capability_receipt_coverage": {"missing": ["swarm"]},
        "semantic_completed": True,
        "run_eligible": True,
        "model_uses_nexus": True,
    }

    apply_contracts_to_row(row)

    assert row["receipt_data_contract_status"] == "DATA_CONTRACT_VIOLATION"
    assert row["receipt_data_contract_missing"] == ["swarm"]
    assert row["token_data_contract_status"] == "DATA_CONTRACT_VIOLATION"
    assert row["data_contract_violation"] is True
    assert row["data_contract_violation_reasons"] == [
        "missing_expected_capability_receipts",
        "model_call_without_measured_provider_tokens",
    ]
    assert row["rubric_contract_status"] == "RETURN"
    assert row["rubric_contract_hard_fail_reasons"] == [
        "missing_required_capability_receipts",
        "token_telemetry_incomplete",
    ]


def test_build_rubric_contract_keeps_local_no_model_cost_not_applicable():
    row = {
        "mode": "with_nexus",
        "model_calls": 0,
        "total_tokens": 0,
        "expected_capability_receipt_coverage": {"missing": []},
        "expected_capabilities": ["delivery_gate"],
        "semantic_completed": True,
        "run_eligible": True,
        "model_uses_nexus": True,
        "route_decision_schema_version": "nexus_route_decision_v1",
    }

    apply_contracts_to_row(row)
    rubric = build_rubric_contract(row)

    assert row["token_data_contract_status"] == "NOT_APPLICABLE"
    assert row["token_data_contract_reason"] == "no_model_call"
    assert rubric["overall_status"] == "PASS"
    assert rubric["cost_rubric"]["status"] == "PASS"
    assert rubric["cost_rubric"]["required_artifacts"] == []
