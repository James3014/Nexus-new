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
from scripts.ops.build_sf_flash_pair_matrix import DEFAULT_MODEL, RUNNER_CAPABILITY_ALIAS, _runner_args


DEFAULT_LOCAL_COMPARE = Path("docs/reports/NEXUS_SF_FINAL_LOCAL_SKILL_COMPARE_2026-05-21.json")
DEFAULT_TASKS = Path("docs/reports/NEXUS_SF_FINAL_LIVE_COMPARE_TASKS_2026-05-21.json")
DEFAULT_STATUS = Path("docs/reports/NEXUS_SF_FINAL_LIVE_COMPARE_SKILL_STATUS_2026-05-21.json")
DEFAULT_MATRIX = Path("docs/reports/NEXUS_SF_FINAL_LIVE_COMPARE_MATRIX_2026-05-21.json")
FINAL_LIVE_RUNNER_CAPABILITY_ALIAS = {
    **RUNNER_CAPABILITY_ALIAS,
    # The generic judge_panel receipt is pruned when the live fixture does not
    # produce multiple candidate summaries.  Use the executed Flash+Nexus route
    # seam for this final skill-mount compare and keep benchmark/public claims
    # blocked by the report layer.
    "benchmark_meta_opt": "hyper",
}


def _is_repo_local(path: str) -> bool:
    try:
        Path(path).resolve().relative_to(PROJECT_ROOT.resolve())
    except ValueError:
        return False
    return True


def _skill_status(path: str) -> str:
    return "nexus_curated_candidate" if _is_repo_local(path) else "external_reference_candidate"


def _status_row(*, skill_id: str, path: str, capability: str, role: str) -> dict[str, Any]:
    return {
        "name": skill_id,
        "path": path,
        "root": "nexus_repo_local" if _is_repo_local(path) else "external_reference",
        "skill_status": _skill_status(path),
        "test_level": "sf_final_live_compare",
        "action": "ablation_only_compare",
        "capability_mount": FINAL_LIVE_RUNNER_CAPABILITY_ALIAS.get(capability, capability),
        "family": capability,
        "reason_codes": [f"sf_final_live_compare_{role}"],
    }


def _row(
    *,
    tasks_output: Path,
    status_output: Path,
    task_id: str,
    capability: str,
    skill_id: str,
    skill_path: str,
    arm_id: str,
    model: str,
) -> dict[str, Any]:
    runner_capability = FINAL_LIVE_RUNNER_CAPABILITY_ALIAS.get(capability, capability)
    return {
        "row_id": f"{capability}::{task_id}::{arm_id}::{skill_id}",
        "task_ref": {"manifest": str(tasks_output), "task_id": task_id},
        "model": model,
        "capability": capability,
        "sf_route_capability_id": capability,
        "runner_capability_id": runner_capability,
        "arm_id": arm_id,
        "arm_type": "skill_ablation",
        "anonymous_label": arm_id,
        "skill_id": skill_id,
        "source_root": "nexus_repo_local" if _is_repo_local(skill_path) else "external_reference",
        "source_type": _skill_status(skill_path),
        "runtime_eligible": _is_repo_local(skill_path),
        "ablation_eligible": True,
        "skill_mount_requests": [skill_id],
        "runner_env": {
            "NEXUS_VALUE_HIDDEN_VERIFIER": "1",
            "NEXUS_DIRECT_GEMINI_MODEL": model,
            "NEXUS_CAPABILITY_RECEIPT_FIRST": "1",
            "NEXUS_BENCH_SKILL_STATUS_REPORT": str(status_output),
            "NEXUS_BENCH_ALLOW_ABLATION_SKILL_MOUNTS": "1",
            "NEXUS_BENCH_SKILL_MOUNT_REQUESTS": json.dumps([skill_id]),
        },
        "runner_args": _runner_args(tasks_output, task_id, model=model),
        "expected_outcome": "flash_nexus_skill_mount_receipt_chain_complete",
    }


def _replacement_rows(local_compare: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    rows = []
    for row in local_compare.get("compare_rows", []) or []:
        if not isinstance(row, Mapping):
            continue
        if row.get("decision") == "REPLACE_PRIMARY_LOCAL_CANDIDATE":
            rows.append(row)
    return rows


def build_sf_final_live_compare_artifacts(
    *,
    local_compare: Mapping[str, Any],
    tasks_output: Path = DEFAULT_TASKS,
    status_output: Path = DEFAULT_STATUS,
    matrix_output: Path = DEFAULT_MATRIX,
    model: str = DEFAULT_MODEL,
) -> dict[str, Any]:
    tasks: list[dict[str, Any]] = []
    status_rows: list[dict[str, Any]] = []
    matrix_rows: list[dict[str, Any]] = []
    blockers: list[str] = []
    seen_status: set[str] = set()

    for item in _replacement_rows(local_compare):
        capability = str(item.get("capability") or "")
        current_skill = str(item.get("current_primary_skill_id") or "")
        current_path = str(item.get("current_primary_path") or "")
        candidate_skill = str(item.get("candidate_skill_id") or "")
        candidate_path = str(item.get("candidate_path") or "")
        if not all((capability, current_skill, current_path, candidate_skill, candidate_path)):
            blockers.append(f"{capability or 'unknown'}:missing_live_compare_fields")
            continue

        task_id = f"sf-final-live-compare-{capability}-001"
        runner_capability = FINAL_LIVE_RUNNER_CAPABILITY_ALIAS.get(capability, capability)
        tasks.append(
            {
                "id": task_id,
                "task_desc": (
                    f"Use Flash+Nexus to compare current primary skill {current_skill} "
                    f"against local replacement candidate {candidate_skill} for capability {capability}."
                ),
                "target_file": "unused",
                "test_file": "unused",
                "success_criteria": "current_vs_candidate_skill_receipt_trust_token_wall_gate",
                "category": capability,
                "difficulty": "medium",
                "repo_kind": "neutral_fixture",
                "repo": "fixture://sf-final-live-compare",
                "repo_ref": "v1",
                "fixture_kind": "sf_final_live_compare",
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
        )
        for skill_id, skill_path, role in (
            (current_skill, current_path, "current_primary"),
            (candidate_skill, candidate_path, "candidate"),
        ):
            if skill_id not in seen_status:
                status_rows.append(_status_row(skill_id=skill_id, path=skill_path, capability=capability, role=role))
                seen_status.add(skill_id)
        matrix_rows.append(
            _row(
                tasks_output=tasks_output,
                status_output=status_output,
                task_id=task_id,
                capability=capability,
                skill_id=current_skill,
                skill_path=current_path,
                arm_id="current_primary_skill",
                model=model,
            )
        )
        matrix_rows.append(
            _row(
                tasks_output=tasks_output,
                status_output=status_output,
                task_id=task_id,
                capability=capability,
                skill_id=candidate_skill,
                skill_path=candidate_path,
                arm_id="candidate_skill",
                model=model,
            )
        )

    task_manifest = {
        "schema": "nexus.sf_final_live_compare_task_manifest.v1",
        "version": "2026-05-21",
        "frozen": True,
        "benchmark_id": "nexus-sf-final-live-compare-v1",
        "description": "Internal live Flash+Nexus current-primary vs candidate skill comparison. Not a public benchmark.",
        "status": "PASS" if tasks and not blockers else "BLOCKED",
        "summary": {
            "task_count": len(tasks),
            "capability_count": len({task["category"] for task in tasks}),
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
        },
        "tasks": tasks,
    }
    status_report = {
        "schema": "nexus.sf_final_live_compare_skill_status.v1",
        "summary": {
            "skill_count": len(status_rows),
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
        },
        "skills": status_rows,
    }
    matrix = {
        "schema": "nexus.sf_final_live_compare_matrix.v1",
        "status": "PASS" if matrix_rows and not blockers else "BLOCKED",
        "summary": {
            "capability_count": len(tasks),
            "task_count": len(tasks),
            "arm_count": 2,
            "row_count": len(matrix_rows),
            "model": model,
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
            "blocker_count": len(blockers),
        },
        "blockers": blockers,
        "rows": matrix_rows,
    }
    write_json(tasks_output, task_manifest)
    write_json(status_output, status_report)
    write_json(matrix_output, matrix)
    return matrix


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build SF final live Flash+Nexus current-vs-candidate matrix.")
    parser.add_argument("--local-compare", default=str(DEFAULT_LOCAL_COMPARE))
    parser.add_argument("--tasks-output", default=str(DEFAULT_TASKS))
    parser.add_argument("--skill-status-output", default=str(DEFAULT_STATUS))
    parser.add_argument("--matrix-output", default=str(DEFAULT_MATRIX))
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args(argv)
    matrix = build_sf_final_live_compare_artifacts(
        local_compare=read_json(args.local_compare),
        tasks_output=Path(args.tasks_output),
        status_output=Path(args.skill_status_output),
        matrix_output=Path(args.matrix_output),
        model=args.model,
    )
    print(json.dumps({"status": matrix["status"], **matrix["summary"]}, ensure_ascii=False, sort_keys=True))
    return 0 if matrix["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
