from nexus.contracts.learning_experience import (
    CAPABILITY_TAXONOMY,
    build_learning_experience,
    project_model_training,
    project_nexus_policy,
)


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
    assert nexus_projection["s2t_prior_eligible"] is True

    model_projection = project_model_training(exp)
    assert model_projection["training_eligible"] is True
    assert model_projection["targets"] == ["preference_pair", "reward_row"]


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
