from __future__ import annotations

from nexus.services.local_assist_value_matrix import (
    EVALUATION_ARMS,
    EvaluationTask,
    run_comparative_matrix,
)


def _tasks() -> tuple[EvaluationTask, ...]:
    return tuple(
        EvaluationTask(
            task_id=f"m5b-{index}",
            family=family,
            input_payload=f"same-input-{index}",
            workspace_revision="rev-1",
            verifier="python -m pytest -q",
        )
        for index, family in enumerate(
            ("localization", "test-only", "simple-bug", "semantic-bug", "cross-file-bug", "verifier-sensitive", "no-change", "insufficient-context"),
            start=1,
        )
    )


def _runner(task: EvaluationTask) -> dict[str, object]:
    return {
        "verified": task.family != "insufficient-context",
        "first_pass_verified": task.family in {"simple-bug", "test-only", "no-change"},
        "cloud_calls": 1,
        "cloud_retries": 0,
        "cloud_input_tokens": 10,
        "cloud_output_tokens": 5,
        "local_calls": 1,
        "local_model_time_sec": 0.1,
        "wall_time_sec": 0.2,
        "cost": 0.01,
        "agent_interventions": 1,
        "candidate_adopted": True,
        "local_assist_contributed": True,
        "unsafe_suggestion": False,
        "abstained": task.family == "insufficient-context",
        "infrastructure_valid": True,
    }


def test_matrix_runs_same_task_families_through_all_arms() -> None:
    matrix = run_comparative_matrix(
        tasks=_tasks(),
        runners={arm: _runner for arm in EVALUATION_ARMS},
    )
    assert matrix["schema"] == "nexus.local_assist.value_matrix.v1"
    assert matrix["task_count"] == 8
    assert set(matrix["arms"]) == set(EVALUATION_ARMS)
    for arm in EVALUATION_ARMS:
        assert matrix["arms"][arm]["verified_solve_rate"] == 7 / 8
        assert matrix["arms"][arm]["task_versions_match"] is True
        assert matrix["arms"][arm]["verifier_conditions_match"] is True
    assert matrix["value_measured"] is True
    assert matrix["public_claim_allowed"] is False


def test_infrastructure_invalid_rows_are_separated() -> None:
    def invalid_runner(task: EvaluationTask) -> dict[str, object]:
        row = _runner(task)
        if task.task_id == "m5b-1":
            row["infrastructure_valid"] = False
            row["infrastructure_failure"] = "provider_setup"
        return row

    matrix = run_comparative_matrix(
        tasks=_tasks(),
        runners={arm: invalid_runner for arm in EVALUATION_ARMS},
    )
    assert matrix["infrastructure_invalid_rows"] == 5
    for arm in EVALUATION_ARMS:
        assert matrix["arms"][arm]["infrastructure_invalid_rows"] == 1
        assert matrix["arms"][arm]["model_failure_rows"] == 0
        assert matrix["arms"][arm]["verified_rows_counted"] == 6


def test_single_task_never_allows_public_value_claim() -> None:
    task = _tasks()[0]
    matrix = run_comparative_matrix(
        tasks=(task,),
        runners={arm: _runner for arm in EVALUATION_ARMS},
    )
    assert matrix["value_measured"] is False
    assert matrix["public_claim_allowed"] is False
    assert matrix["reason"] == "single_task_insufficient_for_value_claim"
