from __future__ import annotations

from nexus.contracts.hybrid_route import (
    HybridRouteDecision,
    build_hybrid_route_decision,
    validate_hybrid_route_decision,
    RouteMode,
    VerifierResult,
    Authority,
)


class TestHybridRouteDegradationChain:

    def test_hybrid_route_decision_has_degradation_reason_chain_field(self):
        decision = HybridRouteDecision()
        assert hasattr(decision, "degradation_reason_chain")
        assert decision.degradation_reason_chain == ()

    def test_hybrid_route_decision_to_dict_includes_chain(self):
        decision = HybridRouteDecision()
        d = decision.to_dict()
        assert "degradation_reason_chain" in d
        assert d["degradation_reason_chain"] == []

    def test_hybrid_route_decision_with_chain_passes_validation(self):
        payload = build_hybrid_route_decision(
            route_mode=RouteMode.LOCAL_ONLY_EXECUTED,
            verifier_result=VerifierResult.PASS,
            local_model_called=True,
            candidate_output_isolated=True,
            selected_candidate_hash="hash1",
            applied_patch_hash="hash1",
            selected_candidate_hash_matches_applied=True,
            evidence_refs=["ref1"],
            metadata={"degradation_reason_chain": ["keep_full_committee:healthy", "local_only:exhausted"]},
        )
        payload["degradation_reason_chain"] = ["keep_full_committee:healthy", "local_only:exhausted"]
        blockers = validate_hybrid_route_decision(payload)
        assert "degradation_reason_chain" not in str(blockers)

    def test_hybrid_route_decision_validation_no_extra_blocker_for_empty_chain(self):
        payload = build_hybrid_route_decision(
            route_mode=RouteMode.LOCAL_ONLY_EXECUTED,
            verifier_result=VerifierResult.PASS,
            local_model_called=True,
            candidate_output_isolated=True,
            selected_candidate_hash="hash1",
            applied_patch_hash="hash1",
            selected_candidate_hash_matches_applied=True,
            evidence_refs=["ref1"],
        )
        blockers = validate_hybrid_route_decision(payload)
        assert "degradation_reason_chain" not in str(blockers)
