from __future__ import annotations

from nexus.engine.capability_executor_controls import build_execution_plan, build_executor_controls
from nexus.engine.capability_planner import CapabilityPlanner
from nexus.engine.capability_receipts import build_trace_receipts, selected_receipts
from nexus.engine.capability_signals import build_capability_signals


def test_capability_signals_normalize_five_pillar_and_skill_inputs():
    signals = build_capability_signals(
        task_desc="Repair a trust-sensitive cross-module timeout with evidence",
        task_type="bug",
        route={
            "recommended_flow": "hyper_sprint",
            "should_research": True,
            "route_features": {
                "risk_score": 72,
                "adjusted_root_cause_confidence": 0.44,
                "candidate_count": 4,
                "memory_hits": 2,
                "findings_hits": 1,
                "is_cross_module_task": True,
            },
            "capability_stack": {
                "selected_capabilities": ["hyper_sprint"],
                "acceleration_layers": ["ddtree"],
            },
        },
        pillars={"lancedb": {"hits": 3}},
        codeintel={"impact_report_present": True},
        skills=[{"skill_id": "as-test-driven-development", "win_rate": 0.82}],
    )

    assert signals.recommended_flow == "hyper_sprint"
    assert signals.lancedb_hits == 3
    assert signals.memory_hits == 2
    assert signals.findings_hits == 1
    assert signals.codeintel_impact_present is True
    assert signals.skill_candidates == ("as-test-driven-development",)
    assert signals.repair_signal is True
    assert signals.evidence_signal is True


def test_ui_signal_does_not_match_public_substring():
    public_task = build_capability_signals(
        task_desc="Tighten an action filter for ordinary public ops research.",
        task_type="public_ops_research",
        route={},
    )
    ui_task = build_capability_signals(
        task_desc="Validate a UI browser screen for accessibility.",
        task_type="frontend",
        route={},
    )

    assert public_task.ui_signal is False
    assert ui_task.ui_signal is True


def test_executor_controls_are_derived_from_plan_not_raw_keywords():
    plain_plan = {"selected_capabilities": ["baseline"]}
    heavy_plan = CapabilityPlanner().plan(
        task_desc="Simple wording",
        task_type="bug",
        route={
            "recommended_flow": "hyper_sprint",
            "route_features": {"risk_score": 80, "candidate_count": 4, "has_hard_signal": True},
            "capability_stack": {
                "selected_capabilities": ["hyper_sprint", "autoreason"],
                "acceleration_layers": ["ddtree"],
                "governance_layers": ["ultra_review"],
            },
        },
    )

    plain_controls = build_executor_controls(plain_plan)
    heavy_controls = build_executor_controls(heavy_plan)

    assert plain_controls["enable_autoreason_executor"] is False
    assert plain_controls["enable_ddtree_executor"] is False
    assert heavy_controls["enable_autoreason_executor"] is True
    assert heavy_controls["enable_ddtree_executor"] is True
    assert heavy_controls["enable_ultra_review"] is True


def test_selected_receipts_do_not_imply_invocation_or_public_claim_safety():
    plan = CapabilityPlanner().plan(
        task_desc="Cross-module refactor: align swarm ownership, drone handoff, and NightShift fallback.",
        task_type="cross_module_refactor_swarm_drone_nightshift",
        route={
            "recommended_flow": "hyper_sprint",
            "route_features": {"risk_score": 45, "candidate_count": 1, "is_cross_module_task": True},
            "capability_stack": {"selected_capabilities": ["hyper_sprint"]},
        },
    )

    receipts = {item.name: item for item in selected_receipts(plan)}

    assert {"swarm", "drone", "nightshift"} <= set(receipts)
    assert receipts["swarm"].selected is False
    assert receipts["swarm"].invoked is False
    assert receipts["swarm"].evidence_present is False
    assert receipts["swarm"].failure_reason == "pending_executor"
    assert receipts["swarm"].public_claim_safe is False


def test_execution_plan_serializes_selected_capabilities_and_controls():
    plan = CapabilityPlanner().plan(
        task_desc="Fix high-risk credential governance regression",
        task_type="bug",
        route={
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 90, "candidate_count": 1, "has_hard_signal": True},
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
    )

    execution = build_execution_plan(plan).to_dict()

    assert execution["schema_version"] == "nexus_capability_execution_plan_v1"
    assert "ultra_review" in execution["selected_capabilities"]
    assert execution["executor_controls"]["enable_ultra_review"] is True


def test_planner_composes_core_capabilities_from_commercial_lane_signals():
    plan = CapabilityPlanner().plan(
        task_desc=(
            "Public benchmark: repair a cross-module evidence and governance regression. "
            "Use research, code impact, memory lessons, swarm review, drone split work, "
            "nightshift fallback, and stress validation when confidence is low."
        ),
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
        pillars={"lancedb": {"hits": 3}},
        codeintel={"impact_report_present": True},
    )

    selected = set(plan.selected_capabilities)
    assert {
        "research_route",
        "mempalace_gate",
        "artifact_gate",
        "claim_gate",
        "delivery_gate",
        "codeintel",
        "research",
        "hyper",
        "autoreason",
        "ddtree",
        "ultra_review",
        "sandbox",
        "memory",
        "lancedb",
        "belief",
        "swarm",
        "drone",
        "nightshift",
        "stress_test",
        "benchmark",
    } <= selected
    assert {"swarm", "drone", "nightshift"} <= set(plan.pending_capabilities)


def test_planner_covers_public_value_capability_matrix_without_model_calls():
    scenarios = [
        (
            "codeintel",
            "Fix cross-module blast radius regression with dependency graph impact evidence.",
            "cross_module_refactor",
            {
                "risk_score": 60,
                "candidate_count": 2,
                "is_cross_module_task": True,
                "has_hard_signal": True,
            },
            {"impact_report_present": True},
        ),
        (
            "research",
            "Resolve stale docs and source contract conflict with citations and research control.",
            "docs_code_sync",
            {"risk_score": 35, "candidate_count": 1},
            {},
        ),
        (
            "hyper",
            "Repair a flaky timeout self-heal failure with hidden evidence.",
            "bug",
            {"risk_score": 75, "candidate_count": 3, "has_hard_signal": True},
            {},
        ),
        (
            "ultra_review",
            "Refactor credential governance and deny by default authorization behavior.",
            "refactor",
            {"risk_score": 80, "candidate_count": 2, "has_hard_signal": True},
            {},
        ),
        (
            "swarm",
            "Coordinate swarm review for a cross-module ownership conflict.",
            "cross_module_refactor_swarm",
            {"risk_score": 80, "candidate_count": 2, "is_cross_module_task": True},
            {},
        ),
        (
            "drone",
            "Split parallel subtasks with drone handoff artifacts.",
            "cross_module_refactor_drone",
            {"risk_score": 60, "candidate_count": 2, "is_cross_module_task": True},
            {},
        ),
        (
            "nightshift",
            "Nightshift fallback for long critical recovery after repeated failures.",
            "bug",
            {"risk_score": 95, "candidate_count": 2, "has_hard_signal": True},
            {},
        ),
        (
            "ddtree",
            "Repair candidate pruning with DDTree acceleration.",
            "bug",
            {"risk_score": 65, "candidate_count": 4, "has_hard_signal": True},
            {},
        ),
        (
            "autoreason",
            "Autoreason over conflicting evidence and low confidence claim.",
            "bug",
            {"risk_score": 50, "adjusted_root_cause_confidence": 0.4, "candidate_count": 2},
            {},
        ),
    ]

    for expected, task_desc, task_type, route_features, codeintel in scenarios:
        plan = CapabilityPlanner().plan(
            task_desc=task_desc,
            task_type=task_type,
            route={
                "recommended_flow": "hyper_sprint" if route_features.get("has_hard_signal") else "baseline",
                "should_research": expected == "research",
                "route_features": route_features,
                "capability_stack": {
                    "selected_capabilities": ["hyper_sprint", "autoreason"],
                    "acceleration_layers": ["ddtree"] if expected == "ddtree" else [],
                    "governance_layers": ["ultra_review"] if expected == "ultra_review" else [],
                },
            },
            codeintel=codeintel,
        )

        assert expected in set(plan.selected_capabilities)


def test_trace_receipts_promote_only_invoked_evidence_and_gate_chain():
    plan = {
        "selected_capabilities": ["autoreason", "ddtree", "hyper", "ultra_review", "swarm"],
    }

    receipts = {
        item.name: item
        for item in build_trace_receipts(
            plan=plan,
            capabilities={
                "claim_verified": True,
                "hyper_used": True,
                "winner_source": "local_candidate",
                "attempt_count": 2,
                "swarm_used": False,
                "swarm_evidence_count": 0,
            },
            autoreason={"enabled": True, "winner": "candidate-2", "judge_votes": [{"winner": "candidate-2"}]},
            ddtree={"enabled": True, "eligible": True, "selected_candidate_ids": ["candidate-2"], "actual_saved_steps": 1},
            ultra_review={"invoked": True, "gate_passed": True, "report_path": ".nexus/reports/ultra.json"},
        )
    }

    assert receipts["autoreason"].public_claim_safe is True
    assert receipts["ddtree"].public_claim_safe is True
    assert receipts["hyper"].public_claim_safe is True
    assert receipts["hyper"].executor_id == "hyper_sprint"
    assert receipts["ultra_review"].public_claim_safe is True
    assert receipts["swarm"].selected is True
    assert receipts["swarm"].public_claim_safe is False
    assert receipts["swarm"].outcome_contributed is False


def test_core_gate_receipts_require_specific_evidence_before_public_claim():
    plan = {
        "selected_capabilities": ["mempalace_gate", "artifact_gate", "claim_gate", "delivery_gate"],
    }

    missing = {
        item.name: item
        for item in build_trace_receipts(
            plan=plan,
            capabilities={
                "claim_verified": True,
                "pillars": {"mempalace": True, "artifact": True},
            },
        )
    }
    proven = {
        item.name: item
        for item in build_trace_receipts(
            plan=plan,
            capabilities={
                "claim_verified": True,
                "pillars": {"mempalace": True, "artifact": True},
                "mempalace_audit_ref": ".nexus/reports/mempalace/audit.json",
                "artifact_refs": [".nexus/reports/artifacts/claim_bundle.json"],
                "claim_refs": ["claim:semantic_verified"],
                "delivery_refs": [".nexus/reports/delivery/evidence_bundle.json"],
                "delivery_gate_passed": True,
            },
        )
    }

    assert missing["mempalace_gate"].public_claim_safe is False
    assert missing["mempalace_gate"].failure_reason == "invoked_without_evidence"
    assert missing["artifact_gate"].public_claim_safe is False
    assert missing["artifact_gate"].failure_reason == "invoked_without_evidence"
    assert missing["claim_gate"].public_claim_safe is False
    assert missing["claim_gate"].failure_reason == "invoked_without_evidence"
    assert missing["delivery_gate"].public_claim_safe is False
    assert missing["delivery_gate"].failure_reason == "invoked_without_evidence"

    assert proven["mempalace_gate"].public_claim_safe is True
    assert proven["artifact_gate"].public_claim_safe is True
    assert proven["claim_gate"].public_claim_safe is True
    assert proven["delivery_gate"].public_claim_safe is True
    assert proven["delivery_gate"].outcome_contributed is True


def test_knowledge_receipts_keep_signals_separate_from_public_evidence():
    plan = {
        "selected_capabilities": ["memory", "belief", "research", "lancedb"],
    }

    signals_only = {
        item.name: item
        for item in build_trace_receipts(
            plan=plan,
            capabilities={
                "claim_verified": True,
                "memory_hits": 2,
                "belief_confidence": 0.42,
                "research_used": True,
                "lancedb_hits": 3,
            },
        )
    }
    proven = {
        item.name: item
        for item in build_trace_receipts(
            plan=plan,
            capabilities={
                "claim_verified": True,
                "memory_hits": 2,
                "memory_refs": ["memory:lesson-7"],
                "memory_gate_passed": True,
                "belief_confidence": 0.42,
                "belief_refs": ["belief:low_confidence_route"],
                "belief_gate_passed": True,
                "research_used": True,
                "research_refs": [".nexus/reports/research/pack.json"],
                "research_gate_passed": True,
                "lancedb_hits": 3,
                "lancedb_refs": ["lancedb:claim-3"],
                "lancedb_gate_passed": True,
            },
        )
    }

    for name in ("memory", "belief", "research", "lancedb"):
        assert signals_only[name].invoked is True
        assert signals_only[name].public_claim_safe is False
        assert signals_only[name].failure_reason == "invoked_without_evidence"
        assert proven[name].public_claim_safe is True
        assert proven[name].outcome_contributed is True


def test_msa_receipts_explain_selected_but_unproven_capabilities():
    plan = {
        "selected_capabilities": ["swarm", "drone", "nightshift"],
    }

    receipts = {
        item.name: item
        for item in build_trace_receipts(
            plan=plan,
            capabilities={
                "claim_verified": True,
                "swarm_used": False,
                "swarm_evidence_count": 0,
                "drone_used": True,
                "drone_invoked_count": 0,
                "nightshift_recommended": True,
                "nightshift_invoked": False,
                "nightshift_recovered": False,
                "nightshift_failure_reason": "recommended_without_report",
            },
        )
    }

    assert receipts["swarm"].public_claim_safe is False
    assert receipts["swarm"].failure_reason == "selected_without_invocation"
    assert receipts["drone"].public_claim_safe is False
    assert receipts["drone"].failure_reason == "invoked_without_evidence"
    assert receipts["nightshift"].public_claim_safe is False
    assert receipts["nightshift"].failure_reason == "recommended_without_report"


def test_uninvoked_reasoning_receipt_does_not_treat_none_as_evidence():
    plan = {
        "selected_capabilities": ["autoreason", "ultra_review"],
    }

    receipts = {
        item.name: item
        for item in build_trace_receipts(
            plan=plan,
            capabilities={"claim_verified": True},
            autoreason={},
            ultra_review={"recommended": True, "invoked": False, "reason": "feature_flag_disabled"},
        )
    }

    assert receipts["autoreason"].invoked is False
    assert receipts["autoreason"].evidence_refs == ()
    assert receipts["autoreason"].evidence_present is False
    assert receipts["autoreason"].outcome_contributed is False
    assert receipts["ultra_review"].failure_reason == "feature_flag_disabled"
    assert receipts["ultra_review"].outcome_contributed is False


def test_autoreason_disabled_status_is_not_invoked_or_evidenced():
    plan = {
        "selected_capabilities": ["autoreason"],
    }

    receipts = {
        item.name: item
        for item in build_trace_receipts(
            plan=plan,
            capabilities={"claim_verified": True},
            autoreason={"enabled": False, "status": "DISABLED", "winner_id": "candidate-b"},
        )
    }

    receipt = receipts["autoreason"]
    assert receipt.invoked is False
    assert receipt.evidence_present is False
    assert receipt.gate_passed is False
    assert receipt.outcome_contributed is False
    assert receipt.public_claim_safe is False
    assert receipt.failure_reason == "selected_without_invocation"


def test_autoreason_receipt_requires_winner_and_exposes_tournament_context():
    plan = {
        "selected_capabilities": ["autoreason"],
    }

    no_winner = {
        item.name: item
        for item in build_trace_receipts(
            plan=plan,
            capabilities={"claim_verified": True},
            autoreason={"enabled": True, "judge_scores": [{"candidate": "b", "score": 0.4}]},
        )
    }
    with_winner = {
        item.name: item
        for item in build_trace_receipts(
            plan=plan,
            capabilities={"claim_verified": True},
            autoreason={
                "enabled": True,
                "winner_id": "candidate-b",
                "incumbent_id": "candidate-a",
                "judge_scores": [{"candidate": "candidate-b", "score": 0.8}],
                "stop_reason": "a_streak_converged",
            },
        )
    }

    assert no_winner["autoreason"].public_claim_safe is False
    assert no_winner["autoreason"].failure_reason == "evidence_without_gate_pass"
    assert with_winner["autoreason"].public_claim_safe is True
    assert "candidate-b" in with_winner["autoreason"].evidence_refs
    assert "incumbent_id:candidate-a" in with_winner["autoreason"].evidence_refs
    assert "stop_reason:a_streak_converged" in with_winner["autoreason"].evidence_refs


def test_ddtree_receipt_requires_real_candidate_pruning():
    plan = {
        "selected_capabilities": ["ddtree"],
    }

    not_pruned = {
        item.name: item
        for item in build_trace_receipts(
            plan=plan,
            capabilities={"claim_verified": True},
            ddtree={
                "enabled": True,
                "eligible": True,
                "candidate_count": 2,
                "max_candidates": 2,
                "selected_candidate_ids": ["candidate-a"],
                "actual_saved_steps": 0,
            },
        )
    }
    pruned = {
        item.name: item
        for item in build_trace_receipts(
            plan=plan,
            capabilities={"claim_verified": True},
            ddtree={
                "enabled": True,
                "eligible": True,
                "candidate_count": 4,
                "max_candidates": 2,
                "selected_candidate_ids": ["candidate-a", "candidate-b"],
                "actual_saved_steps": 2,
            },
        )
    }

    assert not_pruned["ddtree"].invoked is False
    assert not_pruned["ddtree"].evidence_present is False
    assert not_pruned["ddtree"].evidence_refs == ()
    assert not_pruned["ddtree"].public_claim_safe is False
    assert not_pruned["ddtree"].failure_reason == "selected_without_invocation"
    assert pruned["ddtree"].invoked is True
    assert pruned["ddtree"].public_claim_safe is True
    assert pruned["ddtree"].failure_reason == ""
    assert "saved_steps:2" in pruned["ddtree"].evidence_refs


def test_ultra_review_receipt_requires_report_evidence_for_outcome():
    plan = {
        "selected_capabilities": ["ultra_review"],
    }

    receipts = {
        item.name: item
        for item in build_trace_receipts(
            plan=plan,
            capabilities={"claim_verified": True},
            ultra_review={"invoked": True, "gate_passed": True, "report_path": ""},
        )
    }

    receipt = receipts["ultra_review"]
    assert receipt.invoked is True
    assert receipt.evidence_present is False
    assert receipt.gate_passed is False
    assert receipt.outcome_contributed is False
    assert receipt.public_claim_safe is False
    assert receipt.failure_reason == "invoked_without_evidence"


def test_msa_receipts_become_public_safe_with_executor_evidence():
    plan = {
        "selected_capabilities": ["swarm", "drone", "nightshift"],
    }

    receipts = {
        item.name: item
        for item in build_trace_receipts(
            plan=plan,
            capabilities={
                "claim_verified": True,
                "swarm_used": True,
                "swarm_evidence_count": 2,
                "swarm_consensus": "pass",
                "swarm_report": {
                    "schema_version": "nexus_swarm_receipt_v1",
                    "evidence_count": 2,
                    "consensus": "pass",
                    "evidence_refs": ["candidate_summary:0", "candidate_summary:1"],
                    "report_path": ".nexus/reports/swarm/x_receipt.json",
                },
                "drone_used": True,
                "drone_invoked_count": 2,
                "drone_artifact_path": ".nexus/reports/drone/run.json",
                "drone_report": {
                    "schema_version": "nexus_drone_receipt_v1",
                    "artifact_count": 2,
                    "artifact_paths": [".nexus/reports/drones/a.json", ".nexus/reports/drones/b.json"],
                    "report_path": ".nexus/reports/drone/x_receipt.json",
                },
                "nightshift_recommended": True,
                "nightshift_invoked": True,
                "nightshift_recovered": True,
                "nightshift_report_path": ".nexus/reports/nightshift/run.json",
                "nightshift_report": {
                    "schema_version": "nexus_nightshift_receipt_v1",
                    "recommended": True,
                    "invoked": True,
                    "recovered": True,
                    "report_path": ".nexus/reports/nightshift/run.json",
                    "failure_reason": "",
                },
            },
        )
    }

    assert receipts["swarm"].public_claim_safe is True
    assert "report:.nexus/reports/swarm/x_receipt.json" in receipts["swarm"].evidence_refs
    assert "candidate_summary:0" in receipts["swarm"].evidence_refs
    assert "role_findings:2" in receipts["swarm"].evidence_refs
    assert receipts["drone"].public_claim_safe is True
    assert "report:.nexus/reports/drone/x_receipt.json" in receipts["drone"].evidence_refs
    assert "artifact:.nexus/reports/drones/a.json" in receipts["drone"].evidence_refs
    assert "subtask_artifact:2" in receipts["drone"].evidence_refs
    assert receipts["nightshift"].public_claim_safe is True
    assert receipts["nightshift"].failure_reason == ""


def test_pending_executor_receipts_do_not_count_as_selected_until_evidence_exists():
    plan = {
        "selected_capabilities": ["swarm", "drone", "nightshift"],
        "pending_capabilities": ["swarm", "drone", "nightshift"],
    }

    receipts = {
        item.name: item
        for item in build_trace_receipts(
            plan=plan,
            capabilities={
                "claim_verified": True,
                "swarm_used": False,
                "swarm_evidence_count": 0,
                "drone_used": True,
                "drone_invoked_count": 0,
                "nightshift_recommended": True,
                "nightshift_invoked": False,
            },
        )
    }

    assert receipts["swarm"].selected is False
    assert receipts["swarm"].failure_reason == "pending_executor"
    assert receipts["drone"].selected is False
    assert receipts["drone"].failure_reason == "pending_executor"
    assert receipts["nightshift"].selected is False
    assert receipts["nightshift"].failure_reason == "pending_executor"
