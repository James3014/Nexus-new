import pytest
import json
from nexus.core.router import SkillsRouter
from nexus.core.belief_contracts import CapabilityReceipt as CoreReceipt
from nexus.engine.capability_contracts import CapabilityReceipt as EngineReceipt
from scripts.bench.public_gate_bundle import derive_cost_efficiency_decision, CostEfficiencyDecision

def test_route_policy_deterministic_rescue_and_candidate_invariants():
    """
    TDD Phase 1 (RED): Verify SkillsRouter supports allow_pre_model_deterministic_rescue contract
    and structures route policy evidence containing capability invariant candidate pools.
    """
    # Initialize SkillsRouter with mock options representing policy controls
    router = SkillsRouter(
        project_root="/Users/jameschen/Workspace/nexus",
        allow_pre_model_deterministic_rescue=True,
        candidate_pool_mode="capability_invariant",  # E.g. "1 LLM + local support"
        governance_hardened_mode="supervised_bare_first"
    )
    
    # Verify the configured policies exist on the router contract interface
    assert hasattr(router, "allow_pre_model_deterministic_rescue")
    assert router.allow_pre_model_deterministic_rescue is True
    assert router.candidate_pool_mode == "capability_invariant"
    
    # Mock routing decision payload representing pre-model rescue
    decision = router.decide_route(
        capability="ast_scanning",
        risk_level="low",
        bare_sufficiency="high",
        hidden_verifier_passed=True
    )
    
    # Route policy evidence must carry reason codes & show it contributed deterministic rescue
    assert "route_execution_policy" in decision
    policy = decision["route_execution_policy"]
    assert "cost_capped_capability_allows_verified_pre_model_rescue" in policy["reason_codes"]
    assert policy["pre_model_deterministic_rescue_allowed"] is True
    assert policy["candidate_pool_size"] == 1  # 1 LLM + local support invariant

def test_telemetry_classification_exclusion_and_provenance():
    """
    TDD Phase 2 (RED): Verify telemetry classification structures network_timeout_observed_ms,
    cost_accounting_exclusion_candidate, and telemetry_provenance on CapabilityReceipt without mutating wall_time_ms.
    """
    # 1. Verify CoreReceipt accepts new classification parameters
    rcpt = CoreReceipt(
        capability_name="test_cap",
        selected=True,
        invoked=True,
        evidence_id="ev_123",
        gate_passed=True,
        telemetries={
            "wall_time_ms": 5000,
            "token_usage": 1000,
            "provider_costs": 0.02,
            "overhead_ms": 300,
            "network_timeout_observed_ms": 3500,
            "cost_accounting_exclusion_candidate": True,
            "telemetry_provenance": "gateway_timeout"
        }
    )
    
    # Ensure wall_time_ms is preserved conservatively (not directly deducted)
    assert rcpt.telemetries["wall_time_ms"] == 5000
    assert rcpt.telemetries["network_timeout_observed_ms"] == 3500
    assert rcpt.telemetries["cost_accounting_exclusion_candidate"] is True
    assert rcpt.telemetries["telemetry_provenance"] == "gateway_timeout"
    assert rcpt.is_claimable is True  # Should still be claimable if telemetry is complete
    
    # 2. Verify derive_cost_efficiency_decision supports exclusion based on reason-code and provenance
    # Scenario A: Valid exclusion provenance -> NOT regressed despite wall_time_ratio over 1.0
    decision_excluded = derive_cost_efficiency_decision(
        delivery_gate_passed=True,
        delivery_gate_failures=[],
        cost_gate_failures=[],
        wall_cost_ratio_with_over_without=1.2,  # Over 1.0, ordinarily REGRESSED
        token_cost_ratio_with_over_without=0.9,
        model_call_ratio_with_over_without=0.9,
        retry_cost_share_wall=0.0,
        retry_cost_share_tokens=0.0,
        wall_ledger_invalid=False,
        warning_ledger_invalid=False,
        valid_comparison_ready=True,
        exclusion_candidate=True,
        exclusion_reason_code="network_timeout_exceeded",
        exclusion_provenance="gateway_timeout"
    )
    
    # The decision status should resolve as IMPROVED or NEUTRAL due to valid exclusion
    assert decision_excluded.status in {"IMPROVED", "NEUTRAL"}
    assert "wall_cost_not_improved" not in decision_excluded.failures
    
    # Scenario B: Invalid provenance -> Still REGRESSED
    decision_failed_exclusion = derive_cost_efficiency_decision(
        delivery_gate_passed=True,
        delivery_gate_failures=[],
        cost_gate_failures=[],
        wall_cost_ratio_with_over_without=1.2,
        token_cost_ratio_with_over_without=0.9,
        model_call_ratio_with_over_without=0.9,
        retry_cost_share_wall=0.0,
        retry_cost_share_tokens=0.0,
        wall_ledger_invalid=False,
        warning_ledger_invalid=False,
        valid_comparison_ready=True,
        exclusion_candidate=True,
        exclusion_reason_code="unknown_reason",
        exclusion_provenance="unregistered_provenance"
    )
    
    assert decision_failed_exclusion.status == "REGRESSED"
    assert "wall_cost_not_improved" in decision_failed_exclusion.failures
