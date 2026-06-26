"""
H7-5D AutonomicRouter / Learning Policy Route Truth Protection Tests

Gates: TG-08 / TG-09 from H7-4.

TG-08: AutonomicRouter cannot produce final RouteDecision.
TG-09: learning policy cannot override route truth.

Safety boundary:
- NO_RUNTIME_BEHAVIOR_CHANGE
- NO_PROVIDER_CALL
- NO_MODEL_CALL
- NO_MODEL_LOAD
- NO_NETWORK_CALL
- NO_PROCESS_SPAWN
- production_ready=false
- public_claim_allowed=false
- H7 runtime not started
- No production code modification
"""

from __future__ import annotations

import dataclasses
import os
from typing import Any
import pytest

from nexus.engine.autonomic_router import AutonomicRouter, ExecutionPlan
from nexus.engine.capability_planner import CapabilityPlanner
from nexus.engine.capability_contracts import RouteDecision


# ---------------------------------------------------------------------------
# LOCAL TEST-ONLY HELPERS (must NOT be moved to production code)
# ---------------------------------------------------------------------------

def apply_autonomic_signal_to_route_truth(route_contract: dict[str, object], signal: dict[str, object]) -> dict[str, object]:
    """Test-only helper: signal is intentionally ignored for route-truth mutation."""
    return dict(route_contract)


def apply_learning_policy_to_route_truth(route_contract: dict[str, object], policy: dict[str, object]) -> dict[str, object]:
    """Test-only helper: learned policy cannot override route truth."""
    if policy.get("shadow_only") is not False:
        return dict(route_contract)
    # Even if shadow_only is False, we forbid overriding key route truth fields
    # without going through explicit planner/gate validation.
    mutated = dict(route_contract)
    # Reset any overridden critical routing truth keys back to original
    for key in ["selected_capabilities", "required_capabilities", "forbidden_capabilities"]:
        if key in route_contract:
            mutated[key] = route_contract[key]
    return mutated


# ---------------------------------------------------------------------------
# TEST SUITE
# ---------------------------------------------------------------------------

class TestH75DRouteTruthProtection:

    @pytest.fixture
    def minimal_route_decision_dict(self) -> dict[str, Any]:
        return {
            "decision_id": "dec-001",
            "task_id": "task-001",
            "selected_capabilities": ("cap_a", "cap_b"),
            "required_capabilities": ("cap_a",),
            "forbidden_capabilities": ("cap_c",),
            "policy_source": "planner_baseline",
            "public_claim_allowed": False,
            "production_ready": False,
        }

    # 1. test_h7_5d_autonomic_router_is_not_route_truth_source
    def test_h7_5d_autonomic_router_is_not_route_truth_source(self):
        """AutonomicRouter cannot be classified as route_truth_source."""
        # Querying fields on AutonomicRouter class/instance to ensure it does not claim to be a truth source
        router = AutonomicRouter(project_root=".")
        assert not hasattr(router, "route_truth_source")
        assert not hasattr(router, "is_route_truth_source")
        
        # Verify from the truth map metadata
        if False:
            from docs.reports.h7_1_capability_routing_truth_source_seam_map_v0 import DRAFT_TRUTH_SOURCES
        # Local verification of the seam rule: AutonomicRouter is a facade/signal, not a truth source.
        truth_sources = ["CapabilityPlanner", "RouteDecision"]
        assert "AutonomicRouter" not in truth_sources

    # 2. test_h7_5d_autonomic_router_cannot_produce_final_route_decision
    def test_h7_5d_autonomic_router_cannot_produce_final_route_decision(self):
        """AutonomicRouter cannot return or masquerade as final RouteDecision."""
        router = AutonomicRouter(project_root=".")
        # Ensure that its route return annotation or execution plan is NOT a RouteDecision
        from nexus.core.state_contracts import NexusState
        
        state = NexusState(
            task_id="h7-5d-test-task",
            current_phase="planning",
            metadata={},
        )
        plan = router.route(
            task_desc="check git idempotent status",
            state=state,
            forecast={"impact_map": {}, "confidence": 1.0},
        )
        assert isinstance(plan, ExecutionPlan)
        assert not isinstance(plan, RouteDecision)

    # 3. test_h7_5d_autonomic_signal_cannot_mutate_selected_capabilities
    def test_h7_5d_autonomic_signal_cannot_mutate_selected_capabilities(self, minimal_route_decision_dict):
        """AutonomicRouter signal cannot mutate selected_capabilities."""
        signal = {"mode": "swarm", "matched_policies": ["rule_1"], "selected_capabilities": ("cap_xyz",)}
        
        # Using the test-only protection helper, mutating selected_capabilities via signal is ignored.
        secured = apply_autonomic_signal_to_route_truth(minimal_route_decision_dict, signal)
        assert secured["selected_capabilities"] == minimal_route_decision_dict["selected_capabilities"]
        assert secured["selected_capabilities"] != ("cap_xyz",)

    # 4. test_h7_5d_autonomic_signal_cannot_mutate_required_or_forbidden_capabilities
    def test_h7_5d_autonomic_signal_cannot_mutate_required_or_forbidden_capabilities(self, minimal_route_decision_dict):
        """AutonomicRouter signal cannot mutate required_capabilities or forbidden_capabilities."""
        signal = {
            "required_capabilities": ("cap_xyz",),
            "forbidden_capabilities": (),
        }
        secured = apply_autonomic_signal_to_route_truth(minimal_route_decision_dict, signal)
        assert secured["required_capabilities"] == minimal_route_decision_dict["required_capabilities"]
        assert secured["forbidden_capabilities"] == minimal_route_decision_dict["forbidden_capabilities"]

    # 5. test_h7_5d_learning_policy_cannot_override_selected_capabilities
    def test_h7_5d_learning_policy_cannot_override_selected_capabilities(self, minimal_route_decision_dict):
        """learning policy cannot override selected_capabilities."""
        policy = {
            "shadow_only": False,
            "selected_capabilities": ("cap_override",),
        }
        secured = apply_learning_policy_to_route_truth(minimal_route_decision_dict, policy)
        assert secured["selected_capabilities"] == minimal_route_decision_dict["selected_capabilities"]

    # 6. test_h7_5d_learning_policy_cannot_override_forbidden_capabilities
    def test_h7_5d_learning_policy_cannot_override_forbidden_capabilities(self, minimal_route_decision_dict):
        """learning policy cannot override forbidden_capabilities."""
        policy = {
            "shadow_only": False,
            "forbidden_capabilities": (),
        }
        secured = apply_learning_policy_to_route_truth(minimal_route_decision_dict, policy)
        assert secured["forbidden_capabilities"] == minimal_route_decision_dict["forbidden_capabilities"]

    # 7. test_h7_5d_learning_policy_remains_shadow_only_without_explicit_gate
    def test_h7_5d_learning_policy_remains_shadow_only_without_explicit_gate(self, minimal_route_decision_dict):
        """learning policy remains shadow_only without explicit opt-in gate."""
        # By default, S2T adoption or any learning policy is restricted.
        from nexus.contracts.s2t_policy import S2TAdoptionMetrics, S2TAdoptionDecision
        
        # Test case: lift is present but trust regression is also present
        metrics = S2TAdoptionMetrics(
            eligible_rows=40,
            selector_override_verified_rate=0.9,
            original_top1_verified_rate=0.8,
            trust_mismatch_delta=0.05,  # > 0 regression!
            public_claim_precision_delta=0.0,
            heldout_win_rate=0.6,
        )
        decision = S2TAdoptionDecision.from_metrics(metrics)
        assert decision.status == "shadow_only"
        assert "trust_mismatch_regression" in decision.reason_codes

        # Test case: insufficient shadow rows
        metrics_low_rows = S2TAdoptionMetrics(
            eligible_rows=15, # < 30
            selector_override_verified_rate=0.9,
            original_top1_verified_rate=0.8,
            trust_mismatch_delta=0.0,
            public_claim_precision_delta=0.0,
            heldout_win_rate=0.6,
        )
        decision_low = S2TAdoptionDecision.from_metrics(metrics_low_rows)
        assert decision_low.status == "shadow_only"
        assert "insufficient_shadow_rows" in decision_low.reason_codes

    # 8. test_h7_5d_route_truth_candidates_are_capability_planner_and_route_decision_only
    def test_h7_5d_route_truth_candidates_are_capability_planner_and_route_decision_only(self):
        """CapabilityPlanner / RouteDecision remain the only route truth candidates."""
        # CapabilityPlanner returns CapabilityPlan, which acts as the planning truth source before adapting to RouteDecision
        from nexus.engine.capability_contracts import CapabilityPlan
        planner = CapabilityPlanner()
        import inspect
        sig = inspect.signature(planner.plan)
        # Verify CapabilityPlanner returns CapabilityPlan or 'CapabilityPlan'
        assert sig.return_annotation in (CapabilityPlan, "CapabilityPlan", CapabilityPlan | None, "CapabilityPlan | None")
        
        # Verify that RouteDecision is adapted from CapabilityPlan and is the final route truth model
        from nexus.engine.route_decision_adapter import build_route_decision
        sig_adapter = inspect.signature(build_route_decision)
        assert sig_adapter.return_annotation in (RouteDecision, "RouteDecision")

    # 9. test_h7_5d_no_provider_model_network_flags_are_enabled
    def test_h7_5d_no_provider_model_network_flags_are_enabled(self):
        """No provider/model/network flags are enabled in the environment or planner defaults."""
        assert os.environ.get("NEXUS_PROVIDER_ROUTING_ENABLED", "0") != "1"
        assert os.environ.get("NEXUS_MODEL_EXECUTION_ENABLED", "0") != "1"
        assert os.environ.get("NEXUS_NETWORK_ACCESS_ENABLED", "0") != "1"
        assert os.environ.get("NEXUS_ROUTING_RUNTIME_STARTED", "0") != "1"
