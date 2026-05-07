from nexus.contracts.learning_experience import (
    CAPABILITY_TAXONOMY,
    apply_autodata_quality_gate,
    build_learning_experience,
    build_escalation_recommendations,
    project_model_training,
    project_nexus_policy,
)
from nexus.core.learning_steward import LearningSteward


def test_learning_experience_unifies_phase_capability_and_gate_chain() -> None:
    usage_trace = {
        "phase_trace": {"S": "start", "P": "plan", "X": "context", "D": "design", "R": "repair", "A": "audit", "C": "close"},
        "capabilities": {
            "artifact_gate_passed": True,
            "artifact_refs": ["artifact:task:tests_passed"],
            "claim_verified": True,
            "delivery_gate_passed": True,
            "delivery_refs": ["delivery:task:artifact_tests_passed"],
        },
        "s2t": {"trace_path": ".nexus/reports/s2t/runtime_trace.jsonl"},
    }
    receipts = [
        {
            "name": "codeintel",
            "selected": True,
            "invoked": True,
            "evidence_present": True,
            "gate_passed": True,
            "outcome_contributed": True,
            "evidence_refs": ["codeintel:impact"],
        },
        {
            "name": "swarm",
            "selected": True,
            "invoked": False,
            "evidence_present": False,
            "gate_passed": False,
            "outcome_contributed": False,
        },
    ]

    exp = build_learning_experience(
        task_id="task-1",
        task_type="bug",
        usage_trace=usage_trace,
        capability_receipts=receipts,
        route_decision_ref="route:task-1",
        learning_steward_decision="INGEST_SHADOW",
    )

    payload = exp.to_dict()
    assert payload["schema_version"] == "nexus_learning_experience.v1"
    assert payload["phase_continuity"]["complete"] is True
    assert payload["gate_chain"]["artifact"] == "pass"
    assert payload["gate_chain"]["claim"] == "pass"
    assert payload["outcome"] == "verified_success"
    assert payload["capability_lifecycle"][0]["category"] == "recon_context"
    assert payload["capability_lifecycle"][0]["funnel_complete"] is True
    assert payload["capability_lifecycle"][1]["capability"] == "swarm"

    nexus_projection = project_nexus_policy(exp)
    assert nexus_projection["route_weight_updates"] == ["codeintel"]
    assert nexus_projection["capability_penalties"] == ["swarm"]
    assert nexus_projection["escalation_recommendations"] == []
    assert nexus_projection["s2t_prior_eligible"] is True

    model_projection = project_model_training(exp)
    assert model_projection["training_eligible"] is True
    assert model_projection["targets"] == ["preference_pair", "reward_row"]

    decision = LearningSteward().decide_experience(exp)
    assert decision.nexus_action == "PROMOTE_NEXUS"
    assert decision.model_action == "EXPORT_MODEL"


def test_capability_taxonomy_covers_core_route_space() -> None:
    for name in (
        "codeintel",
        "research",
        "hyper",
        "nightshift",
        "swarm",
        "drone",
        "ultra_review",
        "autoreason",
        "ddtree",
        "memory",
        "lancedb",
        "mempalace_gate",
        "belief",
        "artifact_gate",
        "claim_gate",
        "delivery_gate",
        "benchmark",
        "meta_opt",
    ):
        assert name in CAPABILITY_TAXONOMY


def test_learning_experience_escalates_failed_hyper_and_gates_autodata_export() -> None:
    exp = build_learning_experience(
        task_id="task-2",
        task_type="bug",
        usage_trace={
            "phase_trace": {"S": "start", "P": "plan", "X": "context", "D": "design", "R": "repair", "A": "audit", "C": "close"},
            "capabilities": {
                "artifact_gate_passed": True,
                "artifact_refs": ["artifact:task-2"],
                "claim_verified": True,
                "delivery_gate_passed": True,
                "delivery_refs": ["delivery:task-2"],
            },
            "s2t": {"trace_path": ".nexus/reports/s2t/task-2.jsonl"},
        },
        capability_receipts=[
            {
                "name": "hyper",
                "selected": True,
                "invoked": True,
                "evidence_present": True,
                "gate_passed": True,
                "outcome_contributed": False,
                "evidence_refs": ["hyper:attempts"],
            }
        ],
    )

    assert build_escalation_recommendations(exp) == [
        {"from": "hyper", "to": "nightshift", "reason": "hyper_invoked_without_outcome"}
    ]
    decision = LearningSteward().decide_experience(exp)
    assert decision.nexus_action == "INGEST_SHADOW"
    assert decision.model_action == "EXPORT_MODEL"
    assert "no_complete_capability_funnel" in decision.reasons

    gated = apply_autodata_quality_gate(
        project_model_training(exp),
        {
            "task_id": "task-2",
            "eligible_for_training": False,
            "reasons": ["low_step_trajectory"],
            "trajectory_steps": 2,
            "information_density": 0.2,
        },
    )
    assert gated["training_eligible"] is False
    assert gated["targets"] == ["hard_negative"]
    assert gated["autodata_gate"]["status"] == "fail"
