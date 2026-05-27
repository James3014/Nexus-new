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

def test_token_cleanliness_and_outlier_quarantine():
    """
    TDD Phase 3 (RED): Verify Task 1 (P0) token cleanliness and outlier quarantine gates.
    1. Token cleanliness: if model call occurred (model_calls > 0) but tokens are missing (token_usage <= 0 or missing),
       the row is infra-invalid, verify_telemetry is invalid, and is_claimable is False.
    2. Outlier gate: if gateway_token_outlier_reason == "stats_outlier_possible_cumulative",
       verify_telemetry is invalid (is_claimable is False) and public_claim_safe is False.
    """
    # Test case 1: Model call occurred but tokens are 0
    rcpt_missing_tokens = CoreReceipt(
        capability_name="test_cap",
        selected=True,
        invoked=True,
        evidence_id="ev_123",
        gate_passed=True,
        telemetries={
            "wall_time_ms": 5000,
            "token_usage": 0,
            "provider_costs": 0.02,
            "overhead_ms": 300,
            "model_calls": 1,
            "has_infra_invalid": True,
            "infra_invalid_reason": "token_cleanliness_missing_tokens"
        }
    )
    assert rcpt_missing_tokens.verify_telemetry.is_valid is False
    assert rcpt_missing_tokens.is_claimable is False
    
    # Test case 2: Outlier detected
    rcpt_outlier_core = CoreReceipt(
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
            "model_calls": 1,
            "gateway_token_outlier_reason": "stats_outlier_possible_cumulative"
        }
    )
    assert rcpt_outlier_core.verify_telemetry.is_valid is False
    assert rcpt_outlier_core.is_claimable is False

    rcpt_outlier_engine = EngineReceipt(
        name="test_cap",
        selected=True,
        invoked=True,
        evidence_present=True,
        gate_passed=True,
        outcome_contributed=True,
        telemetries={
            "wall_time_ms": 5000,
            "token_usage": 1000,
            "provider_costs": 0.02,
            "overhead_ms": 300,
            "model_calls": 1,
            "gateway_token_outlier_reason": "stats_outlier_possible_cumulative"
        }
    )
    assert rcpt_outlier_engine.public_claim_safe is False

def test_manifest_index_filtering_and_duplicate_safety():
    """
    TDD Task 2 (RED/GREEN): Verify filter_tasks_by_manifest_index successfully parses
    index ranges and comma-separated indices, and handles duplicate task IDs without contamination.
    """
    from scripts.bench.capability_ab_runner import CapabilityTask, filter_tasks_by_manifest_index
    
    # 建立一組含有重複 ID 的 Mock Tasks
    mock_tasks = [
        CapabilityTask(id="task_A", difficulty="easy", task_type="public", task_desc="desc", target_file="", test_file="", success_criteria="", manifest_index=0),
        CapabilityTask(id="task_B", difficulty="easy", task_type="public", task_desc="desc", target_file="", test_file="", success_criteria="", manifest_index=1),
        CapabilityTask(id="task_A", difficulty="easy", task_type="public", task_desc="desc", target_file="", test_file="", success_criteria="", manifest_index=2), # 重複的 ID
        CapabilityTask(id="task_C", difficulty="easy", task_type="public", task_desc="desc", target_file="", test_file="", success_criteria="", manifest_index=3),
        CapabilityTask(id="task_D", difficulty="easy", task_type="public", task_desc="desc", target_file="", test_file="", success_criteria="", manifest_index=4),
    ]
    
    # 測試個別 index 篩選
    res1 = filter_tasks_by_manifest_index(mock_tasks, "0,2")
    assert len(res1) == 2
    assert [t.manifest_index for t in res1] == [0, 2]
    # 即便 A 重複，但因使用 manifest index，第一個和第三個 task A 被精確選出，不影響第二個或其他 task
    assert [t.id for t in res1] == ["task_A", "task_A"]
    
    # 測試 range 篩選
    res2 = filter_tasks_by_manifest_index(mock_tasks, "1-3")
    assert len(res2) == 3
    assert [t.manifest_index for t in res2] == [1, 2, 3]
    assert [t.id for t in res2] == ["task_B", "task_A", "task_C"]
    
    # 測試 "all" 或是空字串
    res3 = filter_tasks_by_manifest_index(mock_tasks, "all")
    assert len(res3) == 5


