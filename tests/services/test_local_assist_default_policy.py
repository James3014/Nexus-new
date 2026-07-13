from __future__ import annotations

from nexus.services.local_assist_default_policy import decide_default_policy
from nexus.services.local_assist_value_matrix import EVALUATION_ARMS, EvaluationTask, run_comparative_matrix


def _tasks() -> tuple[EvaluationTask, ...]:
    return tuple(
        EvaluationTask(
            task_id=f"m5c-{index}",
            family=family,
            input_payload=family,
            workspace_revision="rev-1",
            verifier="python -m pytest -q",
        )
        for index, family in enumerate(("no-change", "localization", "simple-bug", "verifier-sensitive"), start=1)
    )


def _runner(task: EvaluationTask) -> dict[str, object]:
    action = {
        "no-change": "skip",
        "localization": "advisor",
        "simple-bug": "candidate",
        "verifier-sensitive": "verified-subtask",
    }[task.family]
    return {
        "recommended_action": action,
        "verified": True,
        "first_pass_verified": True,
        "cloud_calls": 0,
        "local_calls": 1,
        "local_model_time_sec": 0.1,
        "wall_time_sec": 0.2,
        "cost": 0.01,
        "agent_interventions": 1,
        "candidate_adopted": True,
        "local_assist_contributed": True,
        "unsafe_suggestion": False,
        "abstained": False,
        "infrastructure_valid": True,
    }


def test_policy_decision_is_machine_readable_but_does_not_promote_runtime_defaults() -> None:
    matrix = run_comparative_matrix(tasks=_tasks(), runners={arm: _runner for arm in EVALUATION_ARMS})
    result = decide_default_policy(matrix)
    assert result["status"] == "DECIDED"
    assert result["runtime_defaults_promoted"] is False
    assert result["default_by_action"]["skip"]
    assert result["default_by_action"]["advisor"]
    assert result["default_by_action"]["candidate"]
    assert result["default_by_action"]["verified-subtask"]
    assert result["public_claim_allowed"] is False


def test_weak_or_missing_measurement_does_not_decide_defaults() -> None:
    result = decide_default_policy({"schema": "nexus.local_assist.value_matrix.v1", "value_measured": False})
    assert result["status"] == "INSUFFICIENT_EVIDENCE"
    assert result["runtime_defaults_promoted"] is False
    assert result["reason"] == "value_matrix_not_measured"
