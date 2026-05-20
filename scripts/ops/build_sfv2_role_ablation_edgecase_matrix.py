#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
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
DEFAULT_ROLLUP = Path("docs/reports/NEXUS_SFV2_ROLE_ABLATION_LIVE_ROLLUP_2026-05-20.json")
DEFAULT_TASKS = Path("docs/reports/NEXUS_SFV2_ROLE_ABLATION_EDGECASE_TASK_MANIFEST_2026-05-21.json")
DEFAULT_STATUS = Path("docs/reports/NEXUS_SFV2_ROLE_ABLATION_EDGECASE_SKILL_STATUS_2026-05-21.json")
DEFAULT_MATRIX = Path("docs/reports/NEXUS_SFV2_ROLE_ABLATION_EDGECASE_EXECUTION_MATRIX_2026-05-21.json")


ROLE_EDGECASE = {
    "Scout": {
        "dimension": "physical_scan_and_data_collection",
        "must_cover": "identify the concrete impacted surface, source span, or retrieval target before reasoning",
        "loss_signal": "missing_scan_or_incomplete_impact_surface",
    },
    "Logic": {
        "dimension": "semantic_reasoning_and_decision",
        "must_cover": "explain the decision rule, counterexample, and correctness invariant before proposing the outcome",
        "loss_signal": "missing_decision_invariant_or_counterexample",
    },
    "Audit": {
        "dimension": "boundary_security_and_regression",
        "must_cover": "produce a fail-closed evidence, policy, regression, or claim-boundary check",
        "loss_signal": "missing_boundary_or_regression_guard",
    },
    "primary": {
        "dimension": "capability_primary_specialist",
        "must_cover": "use the primary capability specialist signal rather than a generic helper-only path",
        "loss_signal": "missing_primary_capability_signal",
    },
}


def build_sfv2_role_ablation_edgecase_matrix(
    *,
    probe: Mapping[str, Any],
    rollup: Mapping[str, Any],
    tasks_output: Path = DEFAULT_TASKS,
    status_output: Path = DEFAULT_STATUS,
    matrix_output: Path = DEFAULT_MATRIX,
    model: str = DEFAULT_MODEL,
    max_capabilities: int = 0,
) -> dict[str, Any]:
    unresolved = {
        str(row.get("capability") or "")
        for row in rollup.get("capabilities", []) or []
        if isinstance(row, Mapping) and row.get("interpretation") == "RECEIPT_CLEAN_ROLE_REQUIREDNESS_NOT_PROVEN"
    }
    probe_rows = [
        row
        for row in probe.get("rows", []) or []
        if isinstance(row, Mapping) and str(row.get("capability") or "") in unresolved
    ]
    if max_capabilities > 0:
        probe_rows = probe_rows[:max_capabilities]

    skill_paths = _skill_paths()
    tasks: list[dict[str, Any]] = []
    matrix_rows: list[dict[str, Any]] = []
    blockers: list[str] = []
    for row in probe_rows:
        capability = str(row.get("capability") or "")
        runner_capability = HEEP_RUNNER_CAPABILITY_ALIAS.get(capability, capability)
        arms = [arm for arm in row.get("arms", []) or [] if isinstance(arm, Mapping)]
        full_arm = next((arm for arm in arms if arm.get("arm_id") == "full_assembly"), None)
        minus_arms = [arm for arm in arms if str(arm.get("arm_id") or "").startswith("minus_")]
        if not full_arm or not minus_arms:
            blockers.append(f"{capability}:missing_full_or_minus_arms")
            continue
        for minus_arm in minus_arms:
            role = str(minus_arm.get("dropped_role") or "primary")
            role_slug = _slug(role)
            task_id = f"sfv2-role-edge-{capability}-{role_slug}-001"
            tasks.append(_edge_task(capability=capability, task_id=task_id, runner_capability=runner_capability, role=role))
            for arm in (full_arm, minus_arm):
                matrix_rows.append(
                    _edge_matrix_row(
                        capability=capability,
                        runner_capability=runner_capability,
                        arm=arm,
                        task_id=task_id,
                        tasks_output=tasks_output,
                        status_output=status_output,
                        model=model,
                        role=role,
                    )
                )

    status_report = _status_report(probe_rows, skill_paths=skill_paths)
    task_manifest = {
        "schema": "nexus.sfv2_role_ablation_edgecase_task_manifest.v1",
        "version": "2026-05-21",
        "frozen": True,
        "benchmark_id": "nexus-sfv2-role-ablation-edgecase-v1",
        "description": "Internal SFV2 role-focused edge-case ablation manifest. Not a public benchmark.",
        "status": "PASS" if tasks and not blockers else "BLOCKED",
        "summary": {
            "task_count": len(tasks),
            "capability_count": len({task["category"] for task in tasks}),
            "role_focus_count": len(tasks),
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
        },
        "tasks": tasks,
    }
    matrix = {
        "schema": "nexus.sfv2_role_ablation_edgecase_execution_matrix.v1",
        "status": "PASS" if matrix_rows and not blockers else "BLOCKED",
        "summary": {
            "capability_count": len({row["capability"] for row in matrix_rows}),
            "role_focus_count": len(tasks),
            "row_count": len(matrix_rows),
            "model": model,
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
            "blocker_count": len(blockers),
        },
        "blockers": blockers,
        "claim_boundary": [
            "Internal SFV2 role-focused edge-case ablation only; not a public benchmark.",
            "A role is required only if full assembly remains clean and the matching minus-role row loses reliability, governance, regression, or receipt evidence.",
            "Runtime defaults remain behind HEEP/EMAS apply review.",
        ],
        "rows": matrix_rows,
    }
    write_json(tasks_output, task_manifest)
    write_json(status_output, status_report)
    write_json(matrix_output, matrix)
    return {"tasks": task_manifest, "status": status_report, "matrix": matrix}


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_") or "primary"


def _edge_task(*, capability: str, task_id: str, runner_capability: str, role: str) -> dict[str, Any]:
    edge = ROLE_EDGECASE.get(role, ROLE_EDGECASE["primary"])
    return {
        "id": task_id,
        "task_desc": (
            f"Run SFV2 role-focused edge-case for capability {capability}. "
            f"The {role} role must {edge['must_cover']}. "
            f"Fail the role-requiredness claim if the minus-{role} arm preserves the same evidence chain."
        ),
        "target_file": "unused",
        "test_file": "unused",
        "success_criteria": "all_target_tests_pass",
        "category": capability,
        "difficulty": "medium",
        "repo_kind": "neutral_fixture",
        "repo": "fixture://sfv2-role-ablation-edgecase",
        "repo_ref": "v1",
        "fixture_kind": "sfv2_role_ablation_edgecase_flash_nexus",
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


def _edge_matrix_row(
    *,
    capability: str,
    runner_capability: str,
    arm: Mapping[str, Any],
    task_id: str,
    tasks_output: Path,
    status_output: Path,
    model: str,
    role: str,
) -> dict[str, Any]:
    skill_ids = [str(skill) for skill in arm.get("skill_ids", []) or [] if str(skill)]
    arm_id = str(arm.get("arm_id") or "")
    dropped_role = str(arm.get("dropped_role") or "")
    edge = ROLE_EDGECASE.get(role, ROLE_EDGECASE["primary"])
    runner_env = {
        "NEXUS_VALUE_HIDDEN_VERIFIER": "1",
        "NEXUS_DIRECT_GEMINI_MODEL": model,
        "NEXUS_CAPABILITY_RECEIPT_FIRST": "1",
        "NEXUS_BENCH_SKILL_STATUS_REPORT": str(status_output),
        "NEXUS_BENCH_ALLOW_ABLATION_SKILL_MOUNTS": "1",
        "NEXUS_BENCH_SKILL_MOUNT_REQUESTS": json.dumps(skill_ids, ensure_ascii=False),
        "NEXUS_HEEP_MAT_B_COMPARE": "1",
        "NEXUS_SFV2_ROLE_ABLATION": "1",
        "NEXUS_SFV2_ROLE_EDGECASE": "1",
        "NEXUS_SFV2_ROLE_ABLATION_ARM": arm_id,
        "NEXUS_SFV2_ROLE_FOCUS": role,
        "NEXUS_SFV2_DROPPED_ROLE": dropped_role,
        "NEXUS_SFV2_ROLE_LOSS_SIGNAL": edge["loss_signal"],
    }
    if runner_capability in SWARM_EXECUTOR_RECEIPT_CAPABILITIES:
        runner_env["NEXUS_ENABLE_SWARM_BENCH_EXECUTOR"] = "1"
    return {
        "row_id": f"sfv2-role-edge::{capability}::{task_id}::{arm_id}",
        "task_ref": {"manifest": str(tasks_output), "task_id": task_id},
        "model": model,
        "capability": capability,
        "sf_route_capability_id": capability,
        "runner_capability_id": runner_capability,
        "arm_id": arm_id,
        "arm_type": "role_ablation_edgecase",
        "anonymous_label": arm_id,
        "skill_id": "+".join(skill_ids),
        "source_root": "sfv2_role_ablation_edgecase",
        "source_type": "approved_multi_assembly",
        "runtime_eligible": False,
        "ablation_eligible": True,
        "skill_mount_requests": skill_ids,
        "role_focus": role,
        "role_dimension": edge["dimension"],
        "role_loss_signal": edge["loss_signal"],
        "dropped_role": dropped_role,
        "runner_env": runner_env,
        "runner_args": _runner_args(tasks_output, task_id, model=model),
        "expected_outcome": f"sfv2_role_edgecase::{capability}::{role}::{arm_id}",
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
                        "root": "sfv2_role_ablation_edgecase",
                        "skill_status": "external_reference_candidate",
                        "test_level": "sfv2_role_ablation_edgecase",
                        "action": "ablation_only_compare",
                        "capability_mount": runner_capability,
                        "family": capability,
                        "reason_codes": [
                            "sfv2_role_ablation_edgecase",
                            "not_runtime_default",
                            "not_public_benchmark",
                        ],
                    },
                )
    return {
        "schema": "nexus.sfv2_role_ablation_edgecase_skill_status.v1",
        "summary": {
            "skill_count": len(skills),
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
        },
        "skills": list(skills.values()),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build SFV2 role-focused edge-case ablation matrix.")
    parser.add_argument("--probe", default=str(DEFAULT_PROBE))
    parser.add_argument("--rollup", default=str(DEFAULT_ROLLUP))
    parser.add_argument("--tasks-output", default=str(DEFAULT_TASKS))
    parser.add_argument("--status-output", default=str(DEFAULT_STATUS))
    parser.add_argument("--matrix-output", default=str(DEFAULT_MATRIX))
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--max-capabilities", type=int, default=0)
    args = parser.parse_args(argv)
    artifacts = build_sfv2_role_ablation_edgecase_matrix(
        probe=read_json(args.probe),
        rollup=read_json(args.rollup),
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
