from nexus.core.state_contracts import NexusState
from nexus.health.diagnostics import HealthDiagnostics
from nexus.health.scoring import HealthScorer


def test_diagnostics_prefers_audit_failure_for_rejected_review():
    state = NexusState(task_id="diag-audit")
    state.metadata["last_review_status"] = "REJECTED"
    state.phase_metrics["A"].signals["regression_pass_rate"] = 0.0
    state.phase_metrics["A"].signals["side_effect_score"] = 10.0
    state.phase_metrics["R"].signals["fix_success_rate"] = 0.0

    snapshot = HealthScorer.build_snapshot(state)
    diagnosis = HealthDiagnostics.diagnose(state, snapshot)

    assert diagnosis.kind == "audit_failure"
    assert diagnosis.target_phase == "A"


def test_diagnostics_marks_missing_token_capture_as_evidence_failure():
    state = NexusState(task_id="diag-evidence")
    state.steps_history = []
    state.metadata["last_review_status"] = "APPROVED"
    state.health_metrics.test_pass_rate = 1.0
    state.total_token_usage = 0
    state.token_capture_status = "unknown"

    snapshot = HealthScorer.build_snapshot(state)
    diagnosis = HealthDiagnostics.diagnose(state, snapshot)

    assert diagnosis.kind == "evidence_failure"


def test_diagnostics_returns_insufficient_signals_for_fresh_state():
    state = NexusState(task_id="diag-fresh")

    snapshot = HealthScorer.build_snapshot(state)
    diagnosis = HealthDiagnostics.diagnose(state, snapshot)

    assert diagnosis.kind == "insufficient_signals"


def test_diagnostics_uses_fault_signature_to_choose_environment_failure():
    state = NexusState(task_id="diag-signature")
    state.health_metrics.test_pass_rate = 0.0
    state.metadata["fault_signatures"] = [
        {
            "hash": "abc123",
            "error_type": "ModuleNotFoundError",
            "location": "nexus/core/commander.py:42",
            "traceback_summary": "No module named 'foo'",
        }
    ]
    # Force non-healthy to allow signature path.
    state.phase_metrics["R"].signals["fix_success_rate"] = 0.0
    snapshot = HealthScorer.build_snapshot(state)
    diagnosis = HealthDiagnostics.diagnose(state, snapshot)
    assert diagnosis.kind == "environment_failure"
    assert diagnosis.target_phase == "P"
