#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nexus.learning.skill_fit_closure import read_json, write_json


DEFAULT_CATALOG = Path("docs/reports/NEXUS_SF_FINAL_CAPABILITY_SKILL_CATALOG_V2_2026-05-18.json")
DEFAULT_LOCAL_MATRIX = Path("docs/reports/NEXUS_SF_CAPABILITY_LOCAL_TEST_MATRIX_2026-05-18.json")
DEFAULT_TASKS = Path("docs/reports/NEXUS_SF_FLASH_PAIR_TASK_MANIFEST_2026-05-18.json")
DEFAULT_STATUS = Path("docs/reports/NEXUS_SF_FLASH_PAIR_SKILL_STATUS_2026-05-18.json")
DEFAULT_MATRIX = Path("docs/reports/NEXUS_SF_FLASH_PAIR_EXECUTION_MATRIX_2026-05-18.json")
DEFAULT_MODEL = "gemini-3-flash-preview"
CAPABILITY_FIXTURE_KIND = {
    "learn_ask": "rlm_harder_v2_semantic_searcher_refs",
}
PRIMARY_SKILL_OVERRIDES = {
    "sandbox_replay": {
        "skill_id": "sf2-sandbox_replay-route-fit-spec",
        "skill_path": ".agents/skills/sf2/sf2-sandbox_replay-route-fit-spec/SKILL.md",
        "source_status": "nexus_repo_local",
        "runtime_eligible": False,
    },
}
RUNNER_CAPABILITY_ALIAS = {
    "artifact_gate": "artifact_gate",
    "autonomic_router": "autoreason",
    "autoreason": "autoreason",
    "belief": "belief",
    "benchmark_meta_opt": "judge_panel",
    "claim_gate": "claim_gate",
    "codeintel": "codeintel",
    "ddtree": "ddtree",
    "delivery_acceptance_gate": "delivery_gate",
    "direct_master_loop": "hyper",
    "drone": "drone",
    "external_productivity": "research",
    "file_lock_security_gate": "ultra_review",
    "forecast_pregate": "autoreason",
    "hyper_sprint": "hyper",
    "lancedb": "lancedb",
    "learn_ask": "semantic_searcher",
    "learning_closure": "semantic_failure_sensor",
    "memory": "memory",
    "mempalace": "mempalace_gate",
    "metabolism_resume": "semantic_failure_sensor",
    "nightshift": "nightshift",
    "policy_capability_gate": "mempalace_gate",
    "registry_skills_sync": "semantic_searcher",
    "regression_guard": "semantic_failure_sensor",
    "repair_loop": "hyper",
    "research": "research",
    "research_control_plane": "research",
    "sandbox_replay": "harness_preflight_sensor",
    "swarm_multi_agent": "swarm",
    "ui_validator": "ultra_review",
    "ultra_review": "ultra_review",
    "xray": "codeintel",
}


def _primary_rows(local_matrix: dict) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    for row in local_matrix.get("rows", []) or []:
        if not isinstance(row, dict) or row.get("arm_type") != "skill_arm":
            continue
        capability_id = str(row.get("capability_id") or "")
        skill_id = str(row.get("skill_id") or "")
        rows[f"{capability_id}::{skill_id}"] = row
    return rows


def _runner_args(tasks_path: Path, task_id: str, *, model: str) -> list[str]:
    return [
        "uv",
        "run",
        "python",
        "scripts/bench/capability_ab_runner.py",
        "--tasks-file",
        str(tasks_path),
        "--task-id-filter",
        task_id,
        "--max-tasks",
        "1",
        "--timeout-sec",
        "300",
        "--per-task-stop-loss-sec",
        "600",
        "--stop-loss-sec",
        "600",
        "--nexus-only",
        "--gemini-model",
        model,
        "--with-nexus-runner",
        "subprocess",
        "--with-llm-mode",
        "all",
        "--without-mode",
        "gemini",
        "--enable-autoreason-executor",
        "--enable-ddtree-executor",
        "--enable-ultra-review-dry-gate",
        "--llm-candidate-cap",
        "3",
        "--evidence-bundle",
        "--no-progress-log",
    ]


def build_sf_flash_pair_artifacts(
    *,
    catalog: dict,
    local_matrix: dict,
    tasks_output: Path = DEFAULT_TASKS,
    status_output: Path = DEFAULT_STATUS,
    matrix_output: Path = DEFAULT_MATRIX,
    model: str = DEFAULT_MODEL,
) -> dict:
    primary_by_key = _primary_rows(local_matrix)
    tasks = []
    status_rows = []
    rows = []
    blockers = []
    for item in catalog.get("capability_skill_catalog", []) or []:
        if not isinstance(item, dict):
            continue
        capability_id = str(item.get("capability_id") or "")
        override = PRIMARY_SKILL_OVERRIDES.get(capability_id)
        skill_id = str((override or {}).get("skill_id") or item.get("primary_default") or "")
        primary = dict(primary_by_key.get(f"{capability_id}::{skill_id}", {}))
        if override:
            primary.update(override)
        if not skill_id or not primary:
            blockers.append(f"{capability_id}:missing_primary_skill_row")
            continue
        runner_capability = RUNNER_CAPABILITY_ALIAS.get(capability_id, capability_id)
        fixture_kind = CAPABILITY_FIXTURE_KIND.get(capability_id, "sf_flash_pair")
        task_id = f"sf-flash-pair-{capability_id}-001"
        tasks.append(
            {
                "id": task_id,
                "task_desc": (
                    f"Use Flash+Nexus to exercise capability {capability_id}. "
                    "Compare this capability-only run with the paired primary-skill run."
                ),
                "target_file": "unused",
                "test_file": "unused",
                "success_criteria": "flash_nexus_skill_fit_pair_receipt_chain_complete",
                "category": capability_id,
                "difficulty": "medium",
                "repo_kind": "neutral_fixture",
                "repo": "fixture://sf-flash-pair",
                "repo_ref": "v1",
                "fixture_kind": fixture_kind,
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
        skill_status = "nexus_curated_candidate" if primary.get("runtime_eligible") else "external_reference_candidate"
        status_rows.append(
            {
                "name": skill_id,
                "path": str(primary.get("skill_path") or ""),
                "root": str(primary.get("source_status") or ""),
                "skill_status": skill_status,
                "test_level": "sf_flash_pair",
                "action": "ablation_only_compare",
                "capability_mount": runner_capability,
                "family": capability_id,
                "reason_codes": ["sf_flash_pair_primary"],
            }
        )
        base_env = {
            "NEXUS_VALUE_HIDDEN_VERIFIER": "1",
            "NEXUS_DIRECT_GEMINI_MODEL": model,
            "NEXUS_CAPABILITY_RECEIPT_FIRST": "1",
            "NEXUS_BENCH_SKILL_STATUS_REPORT": str(status_output),
        }
        rows.append(
            {
                "row_id": f"{capability_id}::{task_id}::flash_nexus",
                "task_ref": {"manifest": str(tasks_output), "task_id": task_id},
                "model": model,
                "capability": capability_id,
                "sf_route_capability_id": capability_id,
                "runner_capability_id": runner_capability,
                "arm_id": "flash_nexus",
                "arm_type": "capability_only",
                "anonymous_label": "flash_nexus",
                "skill_id": "",
                "source_root": "",
                "source_type": "",
                "runtime_eligible": False,
                "ablation_eligible": False,
                "skill_mount_requests": [],
                "runner_env": {
                    **base_env,
                    "NEXUS_BENCH_ALLOW_ABLATION_SKILL_MOUNTS": "0",
                    "NEXUS_BENCH_SKILL_MOUNT_REQUESTS": "[]",
                },
                "runner_args": _runner_args(tasks_output, task_id, model=model),
                "expected_outcome": "flash_nexus_without_skill_mount",
            }
        )
        rows.append(
            {
                "row_id": f"{capability_id}::{task_id}::flash_nexus_with_skill::{skill_id}",
                "task_ref": {"manifest": str(tasks_output), "task_id": task_id},
                "model": model,
                "capability": capability_id,
                "sf_route_capability_id": capability_id,
                "runner_capability_id": runner_capability,
                "arm_id": "flash_nexus_with_skill",
                "arm_type": "skill_ablation",
                "anonymous_label": "flash_nexus_with_primary_skill",
                "skill_id": skill_id,
                "source_root": str(primary.get("source_status") or ""),
                "source_type": skill_status,
                "runtime_eligible": bool(primary.get("runtime_eligible")),
                "ablation_eligible": True,
                "skill_mount_requests": [skill_id],
                "runner_env": {
                    **base_env,
                    "NEXUS_BENCH_ALLOW_ABLATION_SKILL_MOUNTS": "1",
                    "NEXUS_BENCH_SKILL_MOUNT_REQUESTS": json.dumps([skill_id]),
                },
                "runner_args": _runner_args(tasks_output, task_id, model=model),
                "expected_outcome": "flash_nexus_with_primary_skill_mount",
            }
        )

    task_manifest = {
        "schema": "nexus.sf_flash_pair_task_manifest.v1",
        "version": "2026-05-18",
        "frozen": True,
        "benchmark_id": "nexus-sf-flash-pair-v1",
        "description": "Internal SF Flash+Nexus vs Flash+Nexus+primary-skill paired matrix. Not a public benchmark.",
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
        "schema": "nexus.sf_flash_pair_skill_status.v1",
        "summary": {
            "skill_count": len(status_rows),
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
        },
        "skills": status_rows,
    }
    matrix = {
        "schema": "nexus.sf_flash_pair_execution_matrix.v1",
        "status": "PASS" if rows and not blockers else "BLOCKED",
        "summary": {
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
        "rows": rows,
    }
    write_json(tasks_output, task_manifest)
    write_json(status_output, status_report)
    write_json(matrix_output, matrix)
    return matrix


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build SF Flash+Nexus vs Flash+Nexus+skill paired matrix.")
    parser.add_argument("--catalog", default=str(DEFAULT_CATALOG))
    parser.add_argument("--local-matrix", default=str(DEFAULT_LOCAL_MATRIX))
    parser.add_argument("--tasks-output", default=str(DEFAULT_TASKS))
    parser.add_argument("--skill-status-output", default=str(DEFAULT_STATUS))
    parser.add_argument("--matrix-output", default=str(DEFAULT_MATRIX))
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args(argv)
    matrix = build_sf_flash_pair_artifacts(
        catalog=read_json(args.catalog),
        local_matrix=read_json(args.local_matrix),
        tasks_output=Path(args.tasks_output),
        status_output=Path(args.skill_status_output),
        matrix_output=Path(args.matrix_output),
        model=args.model,
    )
    print(json.dumps({"status": matrix["status"], **matrix["summary"]}, ensure_ascii=False, sort_keys=True))
    return 0 if matrix["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
