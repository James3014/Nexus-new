"""Comparative value measurement substrate with validity gates."""

from __future__ import annotations

from dataclasses import dataclass, asdict
import json
from pathlib import Path
from typing import Any, Callable, Mapping


EVALUATION_ARMS = (
    "G0_online_agent_bare",
    "G1_nexus_governance",
    "G2_nexus_local_advisor",
    "G3_nexus_full_local_assist",
    "L1_local_only_armor",
)


@dataclass(frozen=True)
class EvaluationTask:
    task_id: str
    family: str
    input_payload: str
    workspace_revision: str
    verifier: str
    version: str = "v1"


def _arm_metrics(rows: list[dict[str, Any]], *, total_task_count: int) -> dict[str, Any]:
    infrastructure_invalid = [row for row in rows if not bool(row.get("infrastructure_valid", True))]
    valid = [row for row in rows if bool(row.get("infrastructure_valid", True))]
    verified = [row for row in valid if bool(row.get("verified", False))]
    first_pass = [row for row in valid if bool(row.get("first_pass_verified", False))]
    total_cost = sum(float(row.get("cost", 0.0) or 0.0) for row in valid)
    return {
        "task_count": total_task_count,
        "verified_rows_counted": len(verified),
        "verified_solve_rate": len(verified) / len(valid) if valid else 0.0,
        "first_pass_verified_rate": len(first_pass) / len(valid) if valid else 0.0,
        "cloud_calls": sum(int(row.get("cloud_calls", 0) or 0) for row in valid),
        "cloud_retries": sum(int(row.get("cloud_retries", 0) or 0) for row in valid),
        "cloud_input_tokens": sum(int(row.get("cloud_input_tokens", 0) or 0) for row in valid),
        "cloud_output_tokens": sum(int(row.get("cloud_output_tokens", 0) or 0) for row in valid),
        "local_calls": sum(int(row.get("local_calls", 0) or 0) for row in valid),
        "local_model_time_sec": sum(float(row.get("local_model_time_sec", 0.0) or 0.0) for row in valid),
        "total_wall_time_sec": sum(float(row.get("wall_time_sec", 0.0) or 0.0) for row in valid),
        "cost_per_verified_solve": total_cost / len(verified) if verified else None,
        "agent_intervention_count": sum(int(row.get("agent_interventions", 0) or 0) for row in valid),
        "candidate_adoption_rate": sum(bool(row.get("candidate_adopted", False)) for row in valid) / len(valid) if valid else 0.0,
        "local_assist_contribution_rate": sum(bool(row.get("local_assist_contributed", False)) for row in valid) / len(valid) if valid else 0.0,
        "unsafe_suggestion_rate": sum(bool(row.get("unsafe_suggestion", False)) for row in valid) / len(valid) if valid else 0.0,
        "abstention_quality": sum(bool(row.get("abstained", False) and not row.get("verified", False)) for row in valid) / max(1, sum(bool(row.get("abstained", False)) for row in valid)),
        "infrastructure_invalid_rows": len(infrastructure_invalid),
        "model_failure_rows": sum(bool(row.get("model_failure", False)) for row in valid),
        "verifier_conditions_match": len({str(row.get("verifier", "")) for row in rows}) <= 1,
        "task_versions_match": len({str(row.get("version", "")) for row in rows}) <= 1,
    }


def run_comparative_matrix(
    *,
    tasks: tuple[EvaluationTask, ...],
    runners: Mapping[str, Callable[[EvaluationTask], Mapping[str, Any]]],
) -> dict[str, Any]:
    if not tasks:
        raise ValueError("evaluation_tasks_missing")
    missing = set(EVALUATION_ARMS) - set(runners)
    if missing:
        raise ValueError("evaluation_arms_missing:" + ",".join(sorted(missing)))
    expected_versions = {task.version for task in tasks}
    expected_verifiers = {task.verifier for task in tasks}
    arms: dict[str, Any] = {}
    all_rows: dict[str, list[dict[str, Any]]] = {}
    infrastructure_invalid_rows = 0
    for arm in EVALUATION_ARMS:
        rows: list[dict[str, Any]] = []
        for task in tasks:
            raw = dict(runners[arm](task) or {})
            row = {
                **raw,
                "task_id": task.task_id,
                "family": task.family,
                "version": task.version,
                "verifier": task.verifier,
                "workspace_revision": task.workspace_revision,
                "arm": arm,
            }
            rows.append(row)
        all_rows[arm] = rows
        infrastructure_invalid_rows += sum(not bool(row.get("infrastructure_valid", True)) for row in rows)
        arms[arm] = _arm_metrics(rows, total_task_count=len(tasks))
    same_task_ids = all(
        [row["task_id"] for row in all_rows[arm]] == [task.task_id for task in tasks]
        for arm in EVALUATION_ARMS
    )
    valid_matrix = (
        len(tasks) >= 2
        and same_task_ids
        and expected_versions == {"v1"}
        and len(expected_verifiers) == 1
        and all(arms[arm]["task_versions_match"] and arms[arm]["verifier_conditions_match"] for arm in EVALUATION_ARMS)
    )
    return {
        "schema": "nexus.local_assist.value_matrix.v1",
        "task_count": len(tasks),
        "task_ids": [task.task_id for task in tasks],
        "task_families": [task.family for task in tasks],
        "arms": arms,
        "infrastructure_invalid_rows": infrastructure_invalid_rows,
        "value_measured": valid_matrix,
        "reason": "" if valid_matrix else "single_task_insufficient_for_value_claim" if len(tasks) < 2 else "matrix_validity_failed",
        "public_claim_allowed": False,
        "production_ready": False,
        "internal_only": True,
        "rows": all_rows,
    }


def write_value_matrix(path: str | Path, matrix: Mapping[str, Any]) -> Path:
    destination = Path(path).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(dict(matrix), indent=2, sort_keys=True), encoding="utf-8")
    return destination
