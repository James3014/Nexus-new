from __future__ import annotations

from nexus.engine.capability_contracts import RouteDecision, RouteExperiment


def test_route_decision_preserves_composable_capability_state():
    decision = RouteDecision(
        schema_version="nexus_route_decision_v1",
        task_id="task-1",
        task_type="cross_module_refactor",
        task_desc_hash="abc123",
        recommended_flow="hyper_sprint",
        decision_source="capability_planner",
        signal_snapshot={"risk_score": 82, "confidence": 0.52},
        selected_capabilities=("codeintel", "autoreason", "ultra_review"),
        required_capabilities=("mempalace_gate", "artifact_gate", "claim_gate"),
        conditional_capabilities=("ddtree", "swarm"),
        pending_capabilities=("drone", "nightshift"),
        forbidden_capabilities=("external_daemon",),
        acceleration_layers=("ddtree",),
        governance_layers=("ultra_review",),
        executor_controls={"enable_autoreason_executor": True, "enable_ultra_review": True},
        constraints=("claim_fail_closed",),
        decision_trace=({"capability": "ultra_review", "reason": "high_risk"},),
        stop_policy={"max_wall_sec": 240, "budget_guard": "fail_closed"},
        receipt_requirements=("invoked", "evidence_present", "gate_passed", "outcome_contributed"),
        fallback_policy="fail_closed",
    ).to_dict()

    assert decision["schema_version"] == "nexus_route_decision_v1"
    assert decision["decision_source"] == "capability_planner"
    assert decision["selected_capabilities"] == ["codeintel", "autoreason", "ultra_review"]
    assert decision["pending_capabilities"] == ["drone", "nightshift"]
    assert decision["public_claim_scope"] == "receipt_backed"
    assert decision["receipt_requirements"] == [
        "invoked",
        "evidence_present",
        "gate_passed",
        "outcome_contributed",
    ]


def test_route_experiment_requires_fixed_eval_and_rollback_context():
    experiment = RouteExperiment(
        schema_version="nexus_route_experiment_v1",
        experiment_id="route-exp-1",
        baseline_route_decision_id="route-old",
        candidate_route_decision_id="route-new",
        variant_source="autoreason_rlm",
        modifiable_scope=("risk_threshold", "ddtree_max_candidates"),
        fixed_eval_manifest="scripts/bench/capability_tasks_cross_module_v1.json",
        seed=7,
        sample_count=12,
        metrics={"semantic_verified_rate": 1.0, "trust_mismatch_rate": 0.0},
        capability_receipts=({"name": "autoreason", "public_claim_safe": True},),
        winner="candidate",
        elimination_matrix=({"variant": "baseline", "reason": "lower_verified_delivery"},),
        rollback_plan={"restore_policy_hash": "old-hash"},
        promotion_decision="promote",
        public_claim_gate={"passed": True},
        failure_lessons=("never_promote_without_receipts",),
    ).to_dict()

    assert experiment["schema_version"] == "nexus_route_experiment_v1"
    assert experiment["modifiable_scope"] == ["risk_threshold", "ddtree_max_candidates"]
    assert experiment["fixed_eval_manifest"].endswith("capability_tasks_cross_module_v1.json")
    assert experiment["rollback_plan"]["restore_policy_hash"] == "old-hash"
    assert experiment["promotion_decision"] == "promote"
    assert experiment["failure_lessons"] == ["never_promote_without_receipts"]
