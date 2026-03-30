from pathlib import Path

from nexus.health.auto_repair import AutoRepairEngine
from nexus.core.state_contracts import NexusState
from nexus.health.models import RepairExecutionResult


def test_analyze_and_suggest_produces_diagnosis_driven_actions():
    state = NexusState(task_id="repair-facade")
    state.metadata["last_review_status"] = "REJECTED"
    state.phase_metrics["A"].signals["regression_pass_rate"] = 0.0
    state.phase_metrics["A"].signals["side_effect_score"] = 10.0
    state.phase_metrics["R"].signals["fix_success_rate"] = 0.0

    suggestions = AutoRepairEngine.analyze_and_suggest(state)

    assert suggestions
    assert suggestions[0]["diagnosis"]["kind"] == "audit_failure"
    assert suggestions[0]["disposition"] == "inject_only"
    assert suggestions[0]["verify_commands"]


def test_execute_repairs_uses_executor_and_records_result(monkeypatch, tmp_path):
    state = NexusState(task_id="repair-exec")
    state.metadata["health_error_kind"] = "environment_failure"

    captured = {}

    def fake_execute(self, plan):
        captured["plan"] = plan
        return RepairExecutionResult(
            disposition="safe_execute",
            executed_actions=[action.id for action in plan.actions],
            notes=["ok"],
        )

    monkeypatch.setattr("nexus.health.executor.RepairExecutor.execute", fake_execute)

    result = AutoRepairEngine.execute_repairs(state, repo_root=tmp_path)

    assert result.disposition == "safe_execute"
    assert captured["plan"].diagnosis.kind == "environment_failure"
    recorded = state.metadata.get("auto_repair_last_result")
    assert recorded is not None
    assert recorded["disposition"] == "safe_execute"
    assert state.auto_actions
