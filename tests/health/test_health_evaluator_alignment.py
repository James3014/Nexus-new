from nexus.core.state_contracts import NexusState
from nexus.engine.health.evaluator import HealthEvaluator


def test_health_evaluator_updates_unified_snapshot_and_score():
    state = NexusState(task_id="health-evaluator")
    state.metadata["last_review_status"] = "APPROVED"
    state.metadata["coverage_signal"] = 80.0
    state.phase_metrics["A"].signals["regression_pass_rate"] = 100.0
    state.phase_metrics["A"].signals["side_effect_score"] = 90.0
    state.total_token_usage = 1000

    score = HealthEvaluator().evaluate(state, success=True)

    snapshot = state.metadata.get("health_snapshot")
    assert snapshot is not None
    assert score == state.health_score
    assert snapshot["overall_score"] == score
    assert state.health_metrics.status in {"HEALTHY", "WARNING", "CRITICAL"}
