from scripts.bench.public_gate_bundle import derive_cost_efficiency_decision


def test_cost_efficiency_decision_passes_when_costs_improve():
    decision = derive_cost_efficiency_decision(
        delivery_gate_passed=True,
        delivery_gate_failures=[],
        cost_gate_failures=[],
        wall_cost_ratio_with_over_without=0.5,
        token_cost_ratio_with_over_without=0.25,
        model_call_ratio_with_over_without=1.0,
        retry_cost_share_wall=0.0,
        retry_cost_share_tokens=0.0,
        wall_ledger_invalid=False,
        warning_ledger_invalid=False,
        valid_comparison_ready=True,
    )

    assert decision.status == "IMPROVED"
    assert decision.failures == []


def test_cost_efficiency_decision_returns_when_wall_ledger_invalid():
    decision = derive_cost_efficiency_decision(
        delivery_gate_passed=True,
        delivery_gate_failures=[],
        cost_gate_failures=[],
        wall_cost_ratio_with_over_without=0.5,
        token_cost_ratio_with_over_without=0.25,
        model_call_ratio_with_over_without=1.0,
        retry_cost_share_wall=0.0,
        retry_cost_share_tokens=0.0,
        wall_ledger_invalid=True,
        warning_ledger_invalid=False,
        valid_comparison_ready=True,
    )

    assert decision.status == "RETURN"
    assert decision.failures == ["wall_ledger_telemetry_invalid"]


def test_cost_efficiency_decision_is_inconclusive_without_valid_comparison():
    decision = derive_cost_efficiency_decision(
        delivery_gate_passed=True,
        delivery_gate_failures=[],
        cost_gate_failures=[],
        wall_cost_ratio_with_over_without=0.5,
        token_cost_ratio_with_over_without=0.25,
        model_call_ratio_with_over_without=1.0,
        retry_cost_share_wall=0.0,
        retry_cost_share_tokens=0.0,
        wall_ledger_invalid=False,
        warning_ledger_invalid=False,
        valid_comparison_ready=False,
    )

    assert decision.status == "INCONCLUSIVE_PROVIDER_VARIANCE"
    assert decision.failures == ["valid_comparison_not_ready"]
