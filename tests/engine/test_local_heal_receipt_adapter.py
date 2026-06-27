from __future__ import annotations

from nexus.contracts.hybrid_route import HybridRouteDecision, RouteMode, VerifierResult, Authority
from nexus.engine.capability_receipt_adapters import LocalHealReceiptAdapter


def test_local_heal_receipt_adapter_legacy_payload() -> None:
    adapter = LocalHealReceiptAdapter()
    
    payload = {
        "repro_log_path": "repro.log",
        "patch_diff_path": "patch.diff",
        "verification_report_path": "report.txt",
        "solve_eligible": True,
        "verification_passed": True,
        "reasoning_mode": "INTUITIVE",
    }
    
    receipt = adapter.build(claim_verified=True, payload=payload)
    assert receipt.name == "local_heal"
    assert receipt.invoked is True
    assert receipt.gate_passed is True
    assert receipt.evidence_present is True
    assert receipt.outcome_contributed is True
    assert receipt.telemetries["reasoning_mode"] == "INTUITIVE"
    assert "hybrid_route_mode" not in receipt.telemetries


def test_local_heal_receipt_adapter_hybrid_route_dict_success() -> None:
    adapter = LocalHealReceiptAdapter()
    
    hybrid_route_dict = {
        "route_mode": "local_only_executed",
        "public_claim_allowed": False,
        "production_ready": False,
        "adapter_output_is_route_truth": False,
        "route_truth_source": "CapabilityPlanner",
        "authority": "internal_only",
        "local_model_called": True,
        "candidate_output_isolated": True,
        "selected_candidate_hash": "hash1",
        "applied_patch_hash": "hash1",
        "selected_candidate_hash_matches_applied": True,
        "verifier_result": "pass",
        "evidence_refs": ["ref1"],
    }
    payload = {"hybrid_route": hybrid_route_dict}
    
    receipt1 = adapter.build(claim_verified=True, payload=payload)
    assert receipt1.invoked is True
    assert receipt1.gate_passed is True
    assert receipt1.outcome_contributed is True
    assert receipt1.telemetries["hybrid_route_mode"] == "local_only_executed"
    assert receipt1.telemetries["hybrid_route_authority"] == "internal_only"
    assert receipt1.telemetries["hybrid_route_verifier_result"] == "pass"

    receipt2 = adapter.build(claim_verified=False, payload=payload)
    assert receipt2.gate_passed is True
    assert receipt2.outcome_contributed is False


def test_local_heal_receipt_adapter_hybrid_route_blocked() -> None:
    adapter = LocalHealReceiptAdapter()
    
    hybrid_route_dict = {
        "route_mode": "local_only_blocked",
        "public_claim_allowed": False,
        "production_ready": False,
        "adapter_output_is_route_truth": False,
        "route_truth_source": "CapabilityPlanner",
        "authority": "trace_only",
        "local_model_called": True,
        "candidate_output_isolated": True,
        "selected_candidate_hash": "hash1",
        "applied_patch_hash": "",
        "selected_candidate_hash_matches_applied": False,
        "verifier_result": "fail",
        "evidence_refs": [],
        "fallback_block_reason": "missing_applied_patch_hash",
    }
    payload = {"hybrid_route": hybrid_route_dict}
    
    receipt = adapter.build(claim_verified=True, payload=payload)
    assert receipt.invoked is True
    assert receipt.gate_passed is False
    assert receipt.outcome_contributed is False
    assert "missing_applied_patch_hash" in receipt.failure_reason


def test_local_heal_receipt_adapter_contract_blocker_fails() -> None:
    adapter = LocalHealReceiptAdapter()
    
    hybrid_route_dict = {
        "route_mode": "cloud_assisted_by_local_trace_only",
        "public_claim_allowed": True,
        "production_ready": False,
        "adapter_output_is_route_truth": False,
        "route_truth_source": "CapabilityPlanner",
        "authority": "trace_only",
    }
    payload = {"hybrid_route": hybrid_route_dict}
    
    receipt = adapter.build(claim_verified=True, payload=payload)
    assert receipt.gate_passed is False
    assert receipt.outcome_contributed is False
    assert "public_claim_allowed_must_be_false" in receipt.failure_reason


def test_local_heal_receipt_adapter_dataclass_payload() -> None:
    adapter = LocalHealReceiptAdapter()
    
    decision = HybridRouteDecision(
        route_mode=RouteMode.CLOUD_ASSISTED_BY_LOCAL_TRACE_ONLY,
        public_claim_allowed=False,
        production_ready=False,
        authority=Authority.TRACE_ONLY,
    )
    payload = {"hybrid_route": decision}
    
    receipt = adapter.build(claim_verified=True, payload=payload)
    assert receipt.gate_passed is False
    assert receipt.telemetries["hybrid_route_mode"] == "cloud_assisted_by_local_trace_only"
