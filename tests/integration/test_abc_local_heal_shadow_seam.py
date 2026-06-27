from __future__ import annotations

import os
from unittest import mock

from nexus.engine.capability_contracts import CapabilityPlan
from nexus.engine.capability_executor_controls import build_execution_plan
from nexus.engine.capability_receipt_adapters import LocalHealReceiptAdapter
from nexus.services.local_heal.capability_adapter import (
    LocalHealCapabilityAdapter,
    LocalHealCapabilityRequest,
)


def test_abc_local_heal_shadow_seam() -> None:
    plan = CapabilityPlan(
        schema_version="nexus_capability_plan_v1",
        selected_capabilities=["local_heal"],
        required_capabilities=["local_heal"],
        optional_capabilities=[],
        conditional_capabilities=[],
        pending_capabilities=[],
        forbidden_capabilities=[],
        constraints=[],
        decision_trace=[],
        replan_trace=[],
        score=95.0,
    )
    
    exe_plan = build_execution_plan(plan)
    
    controls = exe_plan.executor_controls
    assert controls["enable_local_heal"] is True
    assert controls["local_heal_mode"] == "shadow_only"
    assert controls["local_heal_mutation_allowed"] is False
    assert controls["local_heal_receipt_required"] is True
    assert controls["hybrid_route_mode"] == "cloud_assisted_by_local_trace_only"
    assert controls["hybrid_route_authority"] == "trace_only"
    assert controls["hybrid_route_public_claim_allowed"] is False
    assert controls["hybrid_route_production_ready"] is False

    request = LocalHealCapabilityRequest(
        task_id="task-e2e-shadow",
        problem_statement="fix test file",
        evidence_refs=("ref-e2e-1",),
        executor_controls=controls,
    )
    response = LocalHealCapabilityAdapter.run(request)
    
    hr = response.hybrid_route
    assert response.invoked is True
    assert hr.route_mode.value == "local_only_blocked"
    assert hr.authority.value == "trace_only"
    assert "shadow_only_no_runtime" in hr.fallback_block_reason
    assert "mutation_not_allowed" in hr.fallback_block_reason
    
    assert response.capability_payload["adapter_invoked"] is True
    assert response.capability_payload["invoked"] is False
    assert response.hybrid_route.local_model_called is False
    
    adapter = LocalHealReceiptAdapter()
    receipt = adapter.build(claim_verified=False, payload=response.capability_payload)
    
    assert receipt.name == "local_heal"
    assert receipt.selected is True
    assert receipt.invoked is True
    assert receipt.gate_passed is False
    assert receipt.outcome_contributed is False
    
    assert hr.public_claim_allowed is False
    assert hr.production_ready is False
    assert hr.adapter_output_is_route_truth is False
    assert hr.route_truth_source == "CapabilityPlanner"
    assert hr.behavior_changed is False


def test_abc_local_heal_advisory_seam() -> None:
    with mock.patch.dict(os.environ, {"NEXUS_LOCAL_MODEL_ADVISORY_ENABLE": "1"}):
        plan = CapabilityPlan(
            schema_version="nexus_capability_plan_v1",
            selected_capabilities=["local_heal"],
            required_capabilities=["local_heal"],
            optional_capabilities=[],
            conditional_capabilities=[],
            pending_capabilities=[],
            forbidden_capabilities=[],
            constraints=[],
            decision_trace=[],
            replan_trace=[],
            score=95.0,
        )
        
        exe_plan = build_execution_plan(plan)
        controls = exe_plan.executor_controls
        
        request = LocalHealCapabilityRequest(
            task_id="task-e2e-advisory",
            problem_statement="refactor test seam",
            evidence_refs=("ref-e2e-1",),
            executor_controls=controls,
        )
        response = LocalHealCapabilityAdapter.run(request)
        
        hr = response.hybrid_route
        assert response.invoked is True
        assert hr.route_mode.value == "cloud_first_local_guard_advisory"
        assert hr.authority.value == "advisory_only"
        assert hr.behavior_changed is False
        assert hr.adapter_output_is_route_truth is False
        assert response.capability_payload["gate_passed"] is False
        
        adapter = LocalHealReceiptAdapter()
        receipt = adapter.build(claim_verified=False, payload=response.capability_payload)
        
        assert receipt.name == "local_heal"
        assert receipt.selected is True
        assert receipt.invoked is True
        assert receipt.gate_passed is False
        assert receipt.outcome_contributed is False
        assert receipt.public_claim_safe is False


def test_abc_local_heal_fail_closed_seam() -> None:
    with mock.patch.dict(os.environ, {"NEXUS_LOCAL_GUARD_FAIL_CLOSED_ENABLE": "1"}):
        plan = CapabilityPlan(
            schema_version="nexus_capability_plan_v1",
            selected_capabilities=["local_heal"],
            required_capabilities=["local_heal"],
            optional_capabilities=[],
            conditional_capabilities=[],
            pending_capabilities=[],
            forbidden_capabilities=[],
            constraints=[],
            decision_trace=[],
            replan_trace=[],
            score=95.0,
        )
        
        exe_plan = build_execution_plan(plan)
        controls = dict(exe_plan.executor_controls)
        controls["verifier_result"] = "fail"
        
        request = LocalHealCapabilityRequest(
            task_id="task-e2e-fail-closed",
            problem_statement="fix test seam",
            evidence_refs=("ref-e2e-1",),
            executor_controls=controls,
        )
        response = LocalHealCapabilityAdapter.run(request)
        
        hr = response.hybrid_route
        assert response.invoked is True
        assert hr.route_mode.value == "cloud_first_local_guard_fail_closed"
        assert hr.authority.value == "fail_closed"
        assert "verifier_fail" in hr.fallback_block_reason
        assert response.capability_payload["gate_passed"] is False
        
        adapter = LocalHealReceiptAdapter()
        receipt = adapter.build(claim_verified=False, payload=response.capability_payload)
        
        assert receipt.name == "local_heal"
        assert receipt.selected is True
        assert receipt.invoked is True
        assert receipt.gate_passed is False
        assert receipt.outcome_contributed is False
        assert receipt.public_claim_safe is False


def test_abc_local_heal_candidate_seam() -> None:
    with mock.patch.dict(os.environ, {
        "NEXUS_LOCAL_MODEL_CANDIDATE_ENABLE": "1",
        "NEXUS_LOCAL_MODEL_CALL_ALLOWED": "1",
    }):
        plan = CapabilityPlan(
            schema_version="nexus_capability_plan_v1",
            selected_capabilities=["local_heal"],
            required_capabilities=["local_heal"],
            optional_capabilities=[],
            conditional_capabilities=[],
            pending_capabilities=[],
            forbidden_capabilities=[],
            constraints=[],
            decision_trace=[],
            replan_trace=[],
            score=95.0,
        )
        
        exe_plan = build_execution_plan(plan)
        controls = dict(exe_plan.executor_controls)
        
        def mock_gen(req) -> str:
            return "candidate proposal code"
        controls["candidate_generate_fn"] = mock_gen
        
        request = LocalHealCapabilityRequest(
            task_id="task-e2e-candidate",
            problem_statement="fix test seam",
            evidence_refs=("ref-e2e-1",),
            executor_controls=controls,
        )
        response = LocalHealCapabilityAdapter.run(request)
        
        hr = response.hybrid_route
        assert response.invoked is True
        assert hr.route_mode.value == "local_only_blocked"
        assert hr.authority.value == "trace_only"
        assert hr.local_model_called is True
        assert "missing_applied_patch_hash" in hr.fallback_block_reason
        assert "selected_reapply_not_proven" in hr.fallback_block_reason
        assert response.capability_payload["gate_passed"] is False
        
        adapter = LocalHealReceiptAdapter()
        receipt = adapter.build(claim_verified=False, payload=response.capability_payload)
        
        assert receipt.name == "local_heal"
        assert receipt.selected is True
        assert receipt.invoked is True
        assert receipt.gate_passed is False
        assert receipt.outcome_contributed is False
        assert receipt.public_claim_safe is False
