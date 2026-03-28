from nexus.core.phase_health import PhaseHealthCalculator
from nexus.core.state_contracts import NexusState


def test_update_state_uses_unified_health_snapshot_for_rejected_review():
    state = NexusState(task_id="health-facade")
    state.metadata["last_review_status"] = "REJECTED"
    state.phase_metrics["A"].signals["regression_pass_rate"] = 0.0
    state.phase_metrics["A"].signals["side_effect_score"] = 10.0
    state.phase_metrics["R"].signals["fix_success_rate"] = 0.0
    state.phase_metrics["R"].signals["retry_penalty"] = 60.0

    PhaseHealthCalculator.update_state(state)

    snapshot = state.metadata.get("health_snapshot")
    assert snapshot is not None
    assert snapshot["status"] == "CRITICAL"
    assert any(reason.startswith("review_status:") for reason in snapshot["reasons"])
    assert state.health_score <= 45.0
    assert state.pipeline_health >= 0.0


def test_update_state_does_not_invent_optimistic_scores_for_empty_phases():
    state = NexusState(task_id="health-empty")

    PhaseHealthCalculator.update_state(state)

    assert state.phase_metrics["P"].health == 0.0
    assert state.phase_metrics["R"].health == 0.0
    assert state.health_score == 0.0
    assert state.health_metrics.status == "UNKNOWN"
