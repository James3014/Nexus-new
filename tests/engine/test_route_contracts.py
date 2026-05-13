from __future__ import annotations

from nexus.engine.capability_planner import CapabilityPlanner
from nexus.engine.capability_contracts import RouteDecision, RouteExperiment
from nexus.engine.route_decision_adapter import build_route_decision


def test_route_decision_preserves_composable_capability_state():
    decision = RouteDecision(
        schema_version="nexus_route_decision_v1",
        plan_schema_version="nexus_capability_plan_v1",
        plan_mode="dry_run",
        plan_score=42,
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
        misclassification_audit={"schema_version": "nexus_route_misclassification_audit_v1"},
    ).to_dict()

    assert decision["schema_version"] == "nexus_route_decision_v1"
    assert decision["plan_schema_version"] == "nexus_capability_plan_v1"
    assert decision["plan_mode"] == "dry_run"
    assert decision["plan_score"] == 42
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


def test_route_decision_adapter_preserves_full_capability_space():
    plan = CapabilityPlanner().plan(
        task_desc="Cross-module refactor: align swarm, drone, and nightshift fallback.",
        task_type="cross_module_refactor_swarm_drone_nightshift",
        route={
            "recommended_flow": "hyper_sprint",
            "should_research": True,
            "route_features": {
                "risk_score": 92,
                "adjusted_root_cause_confidence": 0.42,
                "candidate_count": 4,
                "memory_hits": 2,
                "findings_hits": 1,
                "is_cross_module_task": True,
                "has_hard_signal": True,
            },
            "capability_stack": {
                "selected_capabilities": ["hyper_sprint", "autoreason"],
                "acceleration_layers": ["ddtree"],
                "governance_layers": ["ultra_review"],
            },
        },
    )
    decision = build_route_decision(
        task_id="task-cross-module",
        task_desc="Cross-module refactor: align swarm, drone, and nightshift fallback.",
        task_type="cross_module_refactor_swarm_drone_nightshift",
        recommended_flow="hyper_sprint",
        plan=plan,
    ).to_dict()

    assert decision["decision_source"] == "capability_planner"
    assert {"research_route", "delivery_gate", "mempalace_gate", "artifact_gate", "claim_gate"} <= set(
        decision["required_capabilities"]
    )
    assert {"autoreason", "ddtree", "ultra_review", "swarm", "drone", "nightshift"} <= set(
        decision["conditional_capabilities"]
    )
    assert not ({"swarm", "drone", "nightshift"} & set(decision["pending_capabilities"]))
    assert "ddtree" in decision["acceleration_layers"]
    assert "ultra_review" in decision["governance_layers"]
    assert decision["stop_policy"]["tactical_sequence"][0] == "hyper_sprint"
    assert "autoreason" in decision["stop_policy"]["tactical_sequence"]
    assert any(
        item["capability"] == "autoreason" and item["evidence_required"]
        for item in decision["stop_policy"]["tactical_tool_map"]
    )
    assert decision["executor_controls"]["enable_autoreason_executor"] is True
    assert decision["executor_controls"]["enable_swarm"] is True
    assert decision["executor_controls"]["enable_drone"] is True
    assert decision["executor_controls"]["enable_nightshift"] is True
    assert decision["fallback_policy"] == "fail_closed"
    assert decision["public_claim_scope"] == "receipt_backed"
    assert decision["plan_schema_version"] == "nexus_capability_plan_v1"
    assert decision["plan_mode"] == "dry_run"
    assert isinstance(decision["plan_score"], int)
    assert decision["derivation_meta"]["routing_tier_fallback_used"] is False
    assert decision["derivation_meta"]["recommended_flow_mismatch"] is False
    assert decision["misclassification_audit"]["schema_version"] == "nexus_route_misclassification_audit_v1"
    assert decision["misclassification_audit"]["high_cost_capabilities_selected"]
    assert any(item["capability"] == "codeintel" for item in decision["decision_trace"])


def test_route_decision_audit_detects_contract_suffix_and_bounded_repair_profile():
    task_desc = (
        "Repair a flaky-looking timeout calculation without deleting assertions."
        "\n\nNexus wearing contract:"
        "\n- Artifact/Claim: treat completion claims as valid only when backed by checks."
    )
    plan = CapabilityPlanner().plan(
        task_desc=task_desc,
        task_type="public_test_repair",
        route={
            "recommended_flow": "hyper_sprint",
            "should_research": False,
            "route_features": {
                "risk_score": 55,
                "adjusted_root_cause_confidence": 0.9,
                "candidate_count": 1,
                "has_hard_signal": True,
            },
            "capability_stack": {"selected_capabilities": ["hyper_sprint"]},
        },
    )
    decision = build_route_decision(
        task_id="task-bounded-repair",
        task_desc=task_desc,
        task_type="public_test_repair",
        recommended_flow="hyper_sprint",
        plan=plan,
    ).to_dict()

    audit = decision["misclassification_audit"]
    assert audit["contract_suffix_detected"] is True
    assert audit["task_body_used_for_lexical_signals"] is True
    assert audit["bounded_repair_profile"] is True
    assert audit["high_cost_capabilities_selected"] == []


def test_route_decision_adapter_records_recommended_flow_mismatch():
    plan = CapabilityPlanner().plan(
        task_desc="Low risk docs alignment",
        task_type="doc-fix",
        route={
            "recommended_flow": "baseline",
            "route_features": {
                "risk_score": 12,
                "adjusted_root_cause_confidence": 0.95,
                "candidate_count": 1,
            },
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
    )
    decision = build_route_decision(
        task_id="task-mismatch",
        task_desc="Low risk docs alignment",
        task_type="doc-fix",
        recommended_flow="hyper_sprint",
        plan=plan,
    ).to_dict()

    assert decision["derivation_meta"]["recommended_flow_plan"] == "baseline"
    assert decision["derivation_meta"]["recommended_flow_param"] == "hyper_sprint"
    assert decision["derivation_meta"]["recommended_flow_mismatch"] is True


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
