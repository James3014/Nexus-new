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
    assert receipts["swarm"].selected is True
    assert receipts["swarm"].invoked is False
    assert receipts["swarm"].evidence_present is False
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


def test_trace_receipts_promote_only_invoked_evidence_and_gate_chain():
    plan = {
        "selected_capabilities": ["autoreason", "ddtree", "ultra_review", "swarm"],
    }

    receipts = {
        item.name: item
        for item in build_trace_receipts(
            plan=plan,
            capabilities={"claim_verified": True, "swarm_used": False, "swarm_evidence_count": 0},
            autoreason={"enabled": True, "winner": "candidate-2", "judge_votes": [{"winner": "candidate-2"}]},
            ddtree={"enabled": True, "eligible": True, "selected_candidate_ids": ["candidate-2"], "actual_saved_steps": 1},
            ultra_review={"invoked": True, "gate_passed": True, "report_path": ".nexus/reports/ultra.json"},
        )
    }

    assert receipts["autoreason"].public_claim_safe is True
    assert receipts["ddtree"].public_claim_safe is True
    assert receipts["ultra_review"].public_claim_safe is True
    assert receipts["swarm"].selected is True
    assert receipts["swarm"].public_claim_safe is False
    assert receipts["swarm"].outcome_contributed is False


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
                "drone_used": True,
                "drone_invoked_count": 2,
                "drone_artifact_path": ".nexus/reports/drone/run.json",
                "nightshift_recommended": True,
                "nightshift_invoked": True,
                "nightshift_recovered": True,
                "nightshift_report_path": ".nexus/reports/nightshift/run.json",
            },
        )
    }

    assert receipts["swarm"].public_claim_safe is True
    assert "role_findings:2" in receipts["swarm"].evidence_refs
    assert receipts["drone"].public_claim_safe is True
    assert "subtask_artifact:2" in receipts["drone"].evidence_refs
    assert receipts["nightshift"].public_claim_safe is True
    assert receipts["nightshift"].failure_reason == ""
