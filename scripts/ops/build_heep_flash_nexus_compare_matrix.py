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


DEFAULT_QUEUE = Path("docs/reports/NEXUS_HEEP_FLASH_NEXUS_LIVE_COMPARE_QUEUE_2026-05-20.json")
DEFAULT_TASKS = Path("docs/reports/NEXUS_HEEP_FLASH_NEXUS_TASK_MANIFEST_2026-05-20.json")
DEFAULT_STATUS = Path("docs/reports/NEXUS_HEEP_FLASH_NEXUS_SKILL_STATUS_2026-05-20.json")
DEFAULT_MATRIX = Path("docs/reports/NEXUS_HEEP_FLASH_NEXUS_EXECUTION_MATRIX_2026-05-20.json")
HEEP_RUNNER_CAPABILITY_ALIAS = {
    **RUNNER_CAPABILITY_ALIAS,
    "governance_and_trust": "mempalace_gate",
    "research_and_source_discipline": "research",
}
SWARM_EXECUTOR_RECEIPT_CAPABILITIES = {"drone", "nightshift", "swarm", "swarm_quiet_moment"}


def _skill_paths() -> dict[str, str]:
    paths: dict[str, str] = {}
    for path in sorted((PROJECT_ROOT / ".agents" / "skills").glob("**/SKILL.md")):
        skill_id = path.parent.name
        paths.setdefault(skill_id, str(path.relative_to(PROJECT_ROOT)))
    return paths


def _arm_skill_ids(arm: Mapping[str, Any]) -> list[str]:
    return [str(skill_id) for skill_id in (arm.get("skill_ids") or []) if str(skill_id).strip()]


def _task_for_candidate(candidate: Mapping[str, Any], *, task_id: str, runner_capability: str) -> dict[str, Any]:
    capability = str(candidate.get("capability") or "")
    return {
        "id": task_id,
        "task_desc": (
            f"Run internal Flash+Nexus MAT-B live compare for capability {capability}. "
            "Compare Mode A current primary against the HEEP multi-skill challenger."
        ),
        "target_file": "unused",
        "test_file": "unused",
        "success_criteria": "all_target_tests_pass",
        "category": capability,
        "difficulty": "medium",
        "repo_kind": "neutral_fixture",
        "repo": "fixture://heep-flash-nexus-compare",
        "repo_ref": "v1",
        "fixture_kind": "heep_mat_b_flash_nexus",
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


def _status_rows(candidates: list[Mapping[str, Any]], *, skill_paths: Mapping[str, str]) -> list[dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        capability = str(candidate.get("capability") or "")
        runner_capability = HEEP_RUNNER_CAPABILITY_ALIAS.get(capability, capability)
        for arm_key in ("baseline_arm", "challenger_arm"):
            for skill_id in _arm_skill_ids(candidate.get(arm_key) or {}):
                rows.setdefault(
                    skill_id,
                    {
                        "name": skill_id,
                        "path": skill_paths.get(skill_id, ""),
                        "root": "heep_mat_b_internal_compare",
                        "skill_status": "external_reference_candidate",
                        "test_level": "heep_flash_nexus_mat_b",
                        "action": "ablation_only_compare",
                        "capability_mount": runner_capability,
                        "family": capability,
                        "reason_codes": [
                            "heep_mat_b_internal_compare",
                            "not_runtime_default",
                            "not_public_benchmark",
                        ],
                    },
                )
    return list(rows.values())


def _matrix_row(
    *,
    candidate: Mapping[str, Any],
    arm: Mapping[str, Any],
    arm_key: str,
    task_id: str,
    tasks_output: Path,
    status_output: Path,
    model: str,
) -> dict[str, Any]:
    capability = str(candidate.get("capability") or "")
    runner_capability = HEEP_RUNNER_CAPABILITY_ALIAS.get(capability, capability)
    skill_ids = _arm_skill_ids(arm)
    arm_id = str(arm.get("arm_id") or arm_key)
    mode = str(arm.get("mode") or "")
    runner_env = {
        "NEXUS_VALUE_HIDDEN_VERIFIER": "1",
        "NEXUS_DIRECT_GEMINI_MODEL": model,
        "NEXUS_CAPABILITY_RECEIPT_FIRST": "1",
        "NEXUS_BENCH_SKILL_STATUS_REPORT": str(status_output),
        "NEXUS_BENCH_ALLOW_ABLATION_SKILL_MOUNTS": "1",
        "NEXUS_BENCH_SKILL_MOUNT_REQUESTS": json.dumps(skill_ids),
        "NEXUS_HEEP_MODE": mode,
        "NEXUS_HEEP_MAT_B_COMPARE": "1",
    }
    if runner_capability in SWARM_EXECUTOR_RECEIPT_CAPABILITIES:
        runner_env["NEXUS_ENABLE_SWARM_BENCH_EXECUTOR"] = "1"
    return {
        "row_id": f"heep::{capability}::{task_id}::{arm_id}",
        "task_ref": {"manifest": str(tasks_output), "task_id": task_id},
        "model": model,
        "capability": capability,
        "sf_route_capability_id": capability,
        "runner_capability_id": runner_capability,
        "arm_id": arm_id,
        "arm_type": "skill_ablation",
        "anonymous_label": arm_id,
        "skill_id": "+".join(skill_ids),
        "source_root": "heep_mat_b_internal_compare",
        "source_type": "external_reference_candidate",
        "runtime_eligible": False,
        "ablation_eligible": True,
        "skill_mount_requests": skill_ids,
        "heep_mode": mode,
        "heep_mat_b_gate": candidate.get("mat_b_gate") or {},
        "runner_env": runner_env,
        "runner_args": _runner_args(tasks_output, task_id, model=model),
        "expected_outcome": f"flash_nexus_internal_heep_compare::{arm_id}",
    }


def build_heep_flash_nexus_compare_artifacts(
    *,
    queue: Mapping[str, Any],
    tasks_output: Path = DEFAULT_TASKS,
    status_output: Path = DEFAULT_STATUS,
    matrix_output: Path = DEFAULT_MATRIX,
    model: str = DEFAULT_MODEL,
    max_candidates: int = 0,
) -> dict[str, Any]:
    candidates = [
        item
        for item in (queue.get("rows") or [])
        if isinstance(item, Mapping) and str(item.get("status") or "") == "READY"
    ]
    if max_candidates > 0:
        candidates = candidates[:max_candidates]
    skill_paths = _skill_paths()
    tasks = []
    rows = []
    blockers = []
    for candidate in candidates:
        capability = str(candidate.get("capability") or "")
        if not capability:
            blockers.append("candidate_missing_capability")
            continue
        baseline = candidate.get("baseline_arm") or {}
        challenger = candidate.get("challenger_arm") or {}
        if not _arm_skill_ids(baseline) or not _arm_skill_ids(challenger):
            blockers.append(f"{capability}:missing_compare_arm_skills")
            continue
        runner_capability = HEEP_RUNNER_CAPABILITY_ALIAS.get(capability, capability)
        task_id = f"heep-mat-b-{capability}-001"
        tasks.append(_task_for_candidate(candidate, task_id=task_id, runner_capability=runner_capability))
        rows.append(
            _matrix_row(
                candidate=candidate,
                arm=baseline,
                arm_key="baseline_arm",
                task_id=task_id,
                tasks_output=tasks_output,
                status_output=status_output,
                model=model,
            )
        )
        rows.append(
            _matrix_row(
                candidate=candidate,
                arm=challenger,
                arm_key="challenger_arm",
                task_id=task_id,
                tasks_output=tasks_output,
                status_output=status_output,
                model=model,
            )
        )
    task_manifest = {
        "schema": "nexus.heep_flash_nexus_task_manifest.v1",
        "version": "2026-05-20",
        "frozen": True,
        "benchmark_id": "nexus-heep-flash-nexus-mat-b-v1",
        "description": "Internal HEEP Mode A vs Mode B/C Flash+Nexus compare manifest. Not a public benchmark.",
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
        "schema": "nexus.heep_flash_nexus_skill_status.v1",
        "summary": {
            "skill_count": len(_status_rows(candidates, skill_paths=skill_paths)),
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
        },
        "skills": _status_rows(candidates, skill_paths=skill_paths),
    }
    matrix = {
        "schema": "nexus.heep_flash_nexus_execution_matrix.v1",
        "status": "PASS" if rows and not blockers else "BLOCKED",
        "summary": {
            "candidate_count": len(candidates),
            "capability_count": len(tasks),
            "task_count": len(tasks),
            "arm_count": 2,
            "row_count": len(rows),
            "model": model,
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
            "blocker_count": len(blockers),
        },
        "blockers": blockers,
        "claim_boundary": [
            "Internal HEEP MAT-B compare only; not a public benchmark.",
            "Rows can request ablation-only skill mounts but cannot update runtime default.",
            "MAT-B verdict requires live success_rate, pollution_pct, evidence_seal_count, token_delta, wall_delta, and reopen_rate evidence.",
        ],
        "rows": rows,
    }
    write_json(tasks_output, task_manifest)
    write_json(status_output, status_report)
    write_json(matrix_output, matrix)
    return {"tasks": task_manifest, "status": status_report, "matrix": matrix}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build internal HEEP Flash+Nexus MAT-B compare matrix.")
    parser.add_argument("--queue", default=str(DEFAULT_QUEUE))
    parser.add_argument("--tasks-output", default=str(DEFAULT_TASKS))
    parser.add_argument("--skill-status-output", default=str(DEFAULT_STATUS))
    parser.add_argument("--matrix-output", default=str(DEFAULT_MATRIX))
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--max-candidates", type=int, default=0)
    args = parser.parse_args(argv)
    artifacts = build_heep_flash_nexus_compare_artifacts(
        queue=read_json(args.queue),
        tasks_output=Path(args.tasks_output),
        status_output=Path(args.skill_status_output),
        matrix_output=Path(args.matrix_output),
        model=args.model,
        max_candidates=args.max_candidates,
    )
    matrix = artifacts["matrix"]
    print(json.dumps({"status": matrix["status"], **matrix["summary"]}, ensure_ascii=False, sort_keys=True))
    return 0 if matrix["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
