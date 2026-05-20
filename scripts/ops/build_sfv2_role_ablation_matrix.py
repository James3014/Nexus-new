#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nexus.learning.skill_fit_closure import read_json, write_json
from scripts.ops.build_heep_flash_nexus_compare_matrix import (
    DEFAULT_MODEL,
    HEEP_RUNNER_CAPABILITY_ALIAS,
    SWARM_EXECUTOR_RECEIPT_CAPABILITIES,
    _runner_args,
    _skill_paths,
)


DEFAULT_PROBE = Path("docs/reports/NEXUS_SFV2_ROLE_ABLATION_PROBE_2026-05-20.json")
DEFAULT_TASKS = Path("docs/reports/NEXUS_SFV2_ROLE_ABLATION_TASK_MANIFEST_2026-05-20.json")
DEFAULT_STATUS = Path("docs/reports/NEXUS_SFV2_ROLE_ABLATION_SKILL_STATUS_2026-05-20.json")
DEFAULT_MATRIX = Path("docs/reports/NEXUS_SFV2_ROLE_ABLATION_EXECUTION_MATRIX_2026-05-20.json")


def build_sfv2_role_ablation_matrix(
    *,
    probe: Mapping[str, Any],
    tasks_output: Path = DEFAULT_TASKS,
    status_output: Path = DEFAULT_STATUS,
    matrix_output: Path = DEFAULT_MATRIX,
    model: str = DEFAULT_MODEL,
    max_capabilities: int = 0,
) -> dict[str, Any]:
    probe_rows = [
        row
        for row in probe.get("rows", []) or []
        if isinstance(row, Mapping) and row.get("role_contribution_state") == "READY_FOR_LIVE_ROLE_ABLATION"
    ]
    if max_capabilities > 0:
        probe_rows = probe_rows[:max_capabilities]
    skill_paths = _skill_paths()
    tasks: list[dict[str, Any]] = []
    matrix_rows: list[dict[str, Any]] = []
    blockers: list[str] = []
    for row in probe_rows:
        capability = str(row.get("capability") or "")
        if not capability:
            blockers.append("probe_row_missing_capability")
            continue
        arms = [arm for arm in row.get("arms", []) or [] if isinstance(arm, Mapping)]
        if not arms:
            blockers.append(f"{capability}:missing_role_ablation_arms")
            continue
        runner_capability = HEEP_RUNNER_CAPABILITY_ALIAS.get(capability, capability)
        task_id = f"sfv2-role-ablation-{capability}-001"
        tasks.append(_task(capability=capability, task_id=task_id, runner_capability=runner_capability))
        for arm in arms:
            matrix_rows.append(
                _matrix_row(
                    capability=capability,
                    runner_capability=runner_capability,
                    arm=arm,
                    task_id=task_id,
                    tasks_output=tasks_output,
                    status_output=status_output,
                    model=model,
                )
            )
    status_report = _status_report(probe_rows, skill_paths=skill_paths)
    task_manifest = {
        "schema": "nexus.sfv2_role_ablation_task_manifest.v1",
        "version": "2026-05-20",
        "frozen": True,
        "benchmark_id": "nexus-sfv2-role-ablation-v1",
        "description": "Internal SFV2 full-vs-minus-role ablation manifest. Not a public benchmark.",
        "status": "PASS" if tasks and not blockers else "BLOCKED",
        "summary": {
            "task_count": len(tasks),
            "capability_count": len({task["category"] for task in tasks}),
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
        },
        "tasks": tasks,
    }
    matrix = {
        "schema": "nexus.sfv2_role_ablation_execution_matrix.v1",
        "status": "PASS" if matrix_rows and not blockers else "BLOCKED",
        "summary": {
            "capability_count": len(tasks),
            "row_count": len(matrix_rows),
            "model": model,
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
            "blocker_count": len(blockers),
        },
        "blockers": blockers,
        "claim_boundary": [
            "Internal SFV2 role-ablation replay only; not a public benchmark.",
            "Role contribution is not proven until full/minus-role rows produce clean MAT-B receipts.",
            "Runtime defaults remain behind runtime apply review.",
        ],
        "rows": matrix_rows,
    }
    write_json(tasks_output, task_manifest)
    write_json(status_output, status_report)
    write_json(matrix_output, matrix)
    return {"tasks": task_manifest, "status": status_report, "matrix": matrix}


def _task(*, capability: str, task_id: str, runner_capability: str) -> dict[str, Any]:
    return {
        "id": task_id,
        "task_desc": (
            f"Run internal SFV2 role-ablation probe for capability {capability}. "
            "Compare the full multi-skill assembly against minus-role arms."
        ),
        "target_file": "unused",
        "test_file": "unused",
        "success_criteria": "all_target_tests_pass",
        "category": capability,
        "difficulty": "medium",
        "repo_kind": "neutral_fixture",
        "repo": "fixture://sfv2-role-ablation",
        "repo_ref": "v1",
        "fixture_kind": "sfv2_role_ablation_flash_nexus",
        "mutation_required": False,
        "allowed_files": ["unused"],
        "forbidden_files": [".nexus/", "logs/", "benchmarks/"],
        "setup_command": "python -V",
        "verification_command": "python -V",
        "expected_capabilities": [runner_capability],
        "capability_activation_contract": "required",
        "eligibility_class": "model_required",
        "public_claim_allowed_metrics": [],
    }


def _matrix_row(
    *,
    capability: str,
    runner_capability: str,
    arm: Mapping[str, Any],
    task_id: str,
    tasks_output: Path,
    status_output: Path,
    model: str,
) -> dict[str, Any]:
    skill_ids = [str(skill) for skill in arm.get("skill_ids", []) or [] if str(skill)]
    arm_id = str(arm.get("arm_id") or "")
    dropped_role = str(arm.get("dropped_role") or "")
    runner_env = {
        "NEXUS_VALUE_HIDDEN_VERIFIER": "1",
        "NEXUS_DIRECT_GEMINI_MODEL": model,
        "NEXUS_CAPABILITY_RECEIPT_FIRST": "1",
        "NEXUS_BENCH_SKILL_STATUS_REPORT": str(status_output),
        "NEXUS_BENCH_ALLOW_ABLATION_SKILL_MOUNTS": "1",
        "NEXUS_BENCH_SKILL_MOUNT_REQUESTS": json.dumps(skill_ids, ensure_ascii=False),
        "NEXUS_HEEP_MAT_B_COMPARE": "1",
        "NEXUS_SFV2_ROLE_ABLATION": "1",
        "NEXUS_SFV2_ROLE_ABLATION_ARM": arm_id,
        "NEXUS_SFV2_DROPPED_ROLE": dropped_role,
    }
    if runner_capability in SWARM_EXECUTOR_RECEIPT_CAPABILITIES:
        runner_env["NEXUS_ENABLE_SWARM_BENCH_EXECUTOR"] = "1"
    return {
        "row_id": f"sfv2-role-ablation::{capability}::{task_id}::{arm_id}",
        "task_ref": {"manifest": str(tasks_output), "task_id": task_id},
        "model": model,
        "capability": capability,
        "sf_route_capability_id": capability,
        "runner_capability_id": runner_capability,
        "arm_id": arm_id,
        "arm_type": "role_ablation",
        "anonymous_label": arm_id,
        "skill_id": "+".join(skill_ids),
        "source_root": "sfv2_role_ablation_internal_probe",
        "source_type": "approved_multi_assembly",
        "runtime_eligible": False,
        "ablation_eligible": True,
        "skill_mount_requests": skill_ids,
        "dropped_role": dropped_role,
        "runner_env": runner_env,
        "runner_args": _runner_args(tasks_output, task_id, model=model),
        "expected_outcome": f"sfv2_role_ablation::{capability}::{arm_id}",
    }


def _status_report(probe_rows: list[Mapping[str, Any]], *, skill_paths: Mapping[str, str]) -> dict[str, Any]:
    skills: dict[str, dict[str, Any]] = {}
    for row in probe_rows:
        capability = str(row.get("capability") or "")
        runner_capability = HEEP_RUNNER_CAPABILITY_ALIAS.get(capability, capability)
        for arm in row.get("arms", []) or []:
            if not isinstance(arm, Mapping):
                continue
            for skill_id in arm.get("skill_ids", []) or []:
                skill_id = str(skill_id)
                if not skill_id:
                    continue
                skills.setdefault(
                    skill_id,
                    {
                        "name": skill_id,
                        "path": skill_paths.get(skill_id, ""),
                        "root": "sfv2_role_ablation_internal_probe",
                        "skill_status": "external_reference_candidate",
                        "test_level": "sfv2_role_ablation",
                        "action": "ablation_only_compare",
                        "capability_mount": runner_capability,
                        "family": capability,
                        "reason_codes": [
                            "sfv2_role_ablation_internal_probe",
                            "not_runtime_default",
                            "not_public_benchmark",
                        ],
                    },
                )
    return {
        "schema": "nexus.sfv2_role_ablation_skill_status.v1",
        "summary": {
            "skill_count": len(skills),
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
        },
        "skills": list(skills.values()),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build SFV2 role-ablation execution matrix.")
    parser.add_argument("--probe", default=str(DEFAULT_PROBE))
    parser.add_argument("--tasks-output", default=str(DEFAULT_TASKS))
    parser.add_argument("--status-output", default=str(DEFAULT_STATUS))
    parser.add_argument("--matrix-output", default=str(DEFAULT_MATRIX))
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--max-capabilities", type=int, default=0)
    args = parser.parse_args(argv)
    artifacts = build_sfv2_role_ablation_matrix(
        probe=read_json(args.probe),
        tasks_output=Path(args.tasks_output),
        status_output=Path(args.status_output),
        matrix_output=Path(args.matrix_output),
        model=args.model,
        max_capabilities=args.max_capabilities,
    )
    matrix = artifacts["matrix"]
    print(json.dumps({"status": matrix["status"], **matrix["summary"], "output": str(args.matrix_output)}, sort_keys=True))
    return 0 if matrix["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
