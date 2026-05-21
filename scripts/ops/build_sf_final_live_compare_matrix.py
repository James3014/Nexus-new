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
from scripts.ops.build_sf_flash_pair_matrix import DEFAULT_MODEL, RUNNER_CAPABILITY_ALIAS, _runner_args


DEFAULT_COMPARE_REPORT = Path("docs/reports/NEXUS_SF_FINAL_COMPARE_REPORT_2026-05-21.json")
DEFAULT_TASKS = Path("docs/reports/NEXUS_SF_FINAL_ALL_CANDIDATE_LIVE_COMPARE_TASKS_2026-05-21.json")
DEFAULT_STATUS = Path("docs/reports/NEXUS_SF_FINAL_ALL_CANDIDATE_LIVE_COMPARE_SKILL_STATUS_2026-05-21.json")
DEFAULT_MATRIX = Path("docs/reports/NEXUS_SF_FINAL_ALL_CANDIDATE_LIVE_COMPARE_MATRIX_2026-05-21.json")
DEFAULT_CLASSIFICATION = Path("docs/reports/NEXUS_SF_FINAL_264_CANDIDATE_CLASSIFICATION_2026-05-21.json")
FINAL_LIVE_RUNNER_CAPABILITY_ALIAS = {
    **RUNNER_CAPABILITY_ALIAS,
    "benchmark_meta_opt": "hyper",
    "governance_and_trust": "mempalace_gate",
    "research_and_source_discipline": "research",
}
PRIMARY_ROLE_BY_CAPABILITY = {
    "artifact_gate": "Audit",
    "claim_gate": "Audit",
    "file_lock_security_gate": "Audit",
    "governance_and_trust": "Audit",
    "mempalace": "Audit",
    "policy_capability_gate": "Audit",
    "regression_guard": "Audit",
    "sandbox_replay": "Audit",
    "ui_validator": "Audit",
    "ultra_review": "Audit",
    "codeintel": "Scout",
    "lancedb": "Scout",
    "learn_ask": "Scout",
    "memory": "Scout",
    "registry_skills_sync": "Scout",
    "research": "Scout",
    "research_and_source_discipline": "Scout",
    "research_control_plane": "Scout",
    "xray": "Scout",
    "autonomic_router": "Logic",
    "autoreason": "Logic",
    "belief": "Logic",
    "benchmark_meta_opt": "Logic",
    "ddtree": "Logic",
    "direct_master_loop": "Logic",
    "drone": "Logic",
    "external_productivity": "Logic",
    "forecast_pregate": "Logic",
    "hyper_sprint": "Logic",
    "learning_closure": "Logic",
    "metabolism_resume": "Logic",
    "nightshift": "Logic",
    "repair_loop": "Logic",
    "swarm_multi_agent": "Logic",
}
ALL_ROLES = ("Scout", "Logic", "Audit")
PRIMARY_MIN_SCORE = 40
SUPPORT_MIN_SCORE = 50


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_")[:120] or "candidate"


def _is_repo_local(path: str) -> bool:
    try:
        Path(path).resolve().relative_to(PROJECT_ROOT.resolve())
    except (OSError, ValueError):
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
        "test_level": "sf_final_all_candidate_live_compare",
        "action": "ablation_only_compare",
        "capability_mount": FINAL_LIVE_RUNNER_CAPABILITY_ALIAS.get(capability, capability),
        "family": capability,
        "reason_codes": [f"sf_final_all_candidate_{role}"],
    }


def _row(
    *,
    tasks_output: Path,
    status_output: Path,
    task_id: str,
    capability: str,
    skill_id: str,
    skill_path: str,
    skill_mount_requests: list[str],
    candidate_skill_id: str,
    arm_id: str,
    model: str,
) -> dict[str, Any]:
    runner_capability = FINAL_LIVE_RUNNER_CAPABILITY_ALIAS.get(capability, capability)
    candidate_suffix = _slug(candidate_skill_id or skill_id)
    return {
        "row_id": f"{capability}::{task_id}::{arm_id}::{candidate_suffix}",
        "task_ref": {"manifest": str(tasks_output), "task_id": task_id},
        "model": model,
        "capability": capability,
        "sf_route_capability_id": capability,
        "runner_capability_id": runner_capability,
        "arm_id": arm_id,
        "arm_type": "skill_ablation",
        "anonymous_label": arm_id,
        "skill_id": skill_id,
        "candidate_skill_id": candidate_skill_id,
        "source_root": "nexus_repo_local" if _is_repo_local(skill_path) else "external_reference",
        "source_type": _skill_status(skill_path),
        "runtime_eligible": _is_repo_local(skill_path),
        "ablation_eligible": True,
        "skill_mount_requests": skill_mount_requests,
        "runner_env": {
            "NEXUS_VALUE_HIDDEN_VERIFIER": "1",
            "NEXUS_DIRECT_GEMINI_MODEL": model,
            "NEXUS_CAPABILITY_RECEIPT_FIRST": "1",
            "NEXUS_BENCH_SKILL_STATUS_REPORT": str(status_output),
            "NEXUS_BENCH_ALLOW_ABLATION_SKILL_MOUNTS": "1",
            "NEXUS_BENCH_SKILL_MOUNT_REQUESTS": json.dumps(skill_mount_requests),
        },
        "runner_args": _runner_args(tasks_output, task_id, model=model),
        "expected_outcome": "flash_nexus_skill_mount_receipt_chain_complete",
    }


def _ready_rows(compare_report: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [
        row
        for row in compare_report.get("compare_rows", []) or []
        if isinstance(row, Mapping) and row.get("decision") == "READY_FOR_LIVE_COMPARE"
    ]


def _first_skill(value: object) -> str:
    if isinstance(value, list) and value:
        return str(value[0] or "")
    return ""


def _need_profile(capability: str) -> dict[str, Any]:
    primary_role = PRIMARY_ROLE_BY_CAPABILITY.get(capability, "Logic")
    support_roles = [role for role in ALL_ROLES if role != primary_role]
    return {
        "capability": capability,
        "primary_roles": [primary_role],
        "support_roles": support_roles,
        "primary_min_score": PRIMARY_MIN_SCORE,
        "support_min_score": SUPPORT_MIN_SCORE,
        "requires_term_fit": True,
    }


def _candidate_classification(item: Mapping[str, Any]) -> dict[str, Any]:
    capability = str(item.get("capability") or "")
    profile = _need_profile(capability)
    role = str(item.get("candidate_role") or "")
    fit_reason = str(item.get("fit_reason") or "")
    try:
        score = int(item.get("static_fit_score") or 0)
    except (TypeError, ValueError):
        score = 0
    source_tier = str(item.get("candidate_source_tier") or item.get("source_tier") or "")
    source_path = str(item.get("canonical_source_path") or "")
    candidate_skill_id = str(item.get("candidate_skill_id") or "")

    verdict = "FILTERED_CAPABILITY_ROLE_MISMATCH"
    reason = f"role {role or 'unknown'} not in primary/support need profile"
    live_eligible = False
    eligibility_rank = 0
    if not fit_reason.startswith("term_hits:"):
        verdict = "FILTERED_COARSE_FIT_ONLY"
        reason = f"fit_reason {fit_reason or 'missing'} is not term-backed"
    elif role in profile["primary_roles"]:
        if score >= profile["primary_min_score"]:
            verdict = "LIVE_ELIGIBLE_PRIMARY_ROLE"
            reason = "candidate role matches primary capability need and term-backed score threshold"
            live_eligible = True
            eligibility_rank = 1
        else:
            verdict = "FILTERED_LOW_STATIC_FIT"
            reason = f"primary role score {score} below {profile['primary_min_score']}"
    elif role in profile["support_roles"]:
        if score >= profile["support_min_score"]:
            verdict = "LIVE_ELIGIBLE_SUPPORT_ROLE"
            reason = "candidate role is accepted support need with stronger term-backed score"
            live_eligible = True
            eligibility_rank = 2
        else:
            verdict = "FILTERED_SUPPORT_ROLE_LOW_STATIC_FIT"
            reason = f"support role score {score} below {profile['support_min_score']}"
    return {
        "capability": capability,
        "candidate_skill_id": candidate_skill_id,
        "candidate_role": role,
        "static_fit_score": score,
        "fit_reason": fit_reason,
        "candidate_source_tier": source_tier,
        "canonical_source_path": source_path,
        "source_type": _skill_status(source_path),
        "need_profile": profile,
        "classification": verdict,
        "classification_reason": reason,
        "live_eligible": live_eligible,
        "eligibility_rank": eligibility_rank,
    }


def build_sf_final_live_compare_artifacts(
    *,
    compare_report: Mapping[str, Any],
    tasks_output: Path = DEFAULT_TASKS,
    status_output: Path = DEFAULT_STATUS,
    matrix_output: Path = DEFAULT_MATRIX,
    classification_output: Path = DEFAULT_CLASSIFICATION,
    model: str = DEFAULT_MODEL,
) -> dict[str, Any]:
    tasks: list[dict[str, Any]] = []
    status_rows: list[dict[str, Any]] = []
    matrix_rows: list[dict[str, Any]] = []
    blockers: list[str] = []
    seen_status: set[str] = set()
    baselines: set[str] = set()
    classifications = [_candidate_classification(item) for item in _ready_rows(compare_report)]
    classification_by_skill = {
        (row["capability"], row["candidate_skill_id"]): row for row in classifications
    }

    for item in _ready_rows(compare_report):
        capability = str(item.get("capability") or "")
        candidate_skill = str(item.get("candidate_skill_id") or "")
        classification = classification_by_skill.get((capability, candidate_skill), {})
        if not classification.get("live_eligible"):
            continue
        baseline_arm = item.get("baseline_arm") if isinstance(item.get("baseline_arm"), Mapping) else {}
        challenger_arm = item.get("challenger_arm") if isinstance(item.get("challenger_arm"), Mapping) else {}
        current_skill = _first_skill(baseline_arm.get("skill_ids"))
        current_path = f".agents/skills/{current_skill}/SKILL.md"
        candidate_path = str(item.get("canonical_source_path") or "")
        challenger_skills = [str(skill) for skill in (challenger_arm.get("skill_ids") or []) if str(skill).strip()]
        if not all((capability, current_skill, candidate_skill, candidate_path, challenger_skills)):
            blockers.append(f"{capability or 'unknown'}:{candidate_skill or 'unknown'}:missing_live_compare_fields")
            continue

        task_id = f"sf-final-all-live-compare-{capability}-001"
        runner_capability = FINAL_LIVE_RUNNER_CAPABILITY_ALIAS.get(capability, capability)
        if capability not in baselines:
            tasks.append(
                {
                    "id": task_id,
                    "task_desc": (
                        f"Use Flash+Nexus to compare current primary skill {current_skill} "
                        f"against all ready candidate skills for capability {capability}."
                    ),
                    "target_file": "unused",
                    "test_file": "unused",
                    "success_criteria": "current_vs_candidate_skill_receipt_trust_token_wall_gate",
                    "category": capability,
                    "difficulty": "medium",
                    "repo_kind": "neutral_fixture",
                    "repo": "fixture://sf-final-all-candidate-live-compare",
                    "repo_ref": "v1",
                    "fixture_kind": "sf_final_all_candidate_live_compare",
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
            matrix_rows.append(
                _row(
                    tasks_output=tasks_output,
                    status_output=status_output,
                    task_id=task_id,
                    capability=capability,
                    skill_id=current_skill,
                    skill_path=current_path,
                    skill_mount_requests=[current_skill],
                    candidate_skill_id="",
                    arm_id="current_primary_skill",
                    model=model,
                )
            )
            baselines.add(capability)
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
                skill_id=candidate_skill,
                skill_path=candidate_path,
                skill_mount_requests=challenger_skills,
                candidate_skill_id=candidate_skill,
                arm_id="candidate_skill",
                model=model,
            )
        )

    task_manifest = {
        "schema": "nexus.sf_final_all_candidate_live_compare_task_manifest.v1",
        "version": "2026-05-21",
        "frozen": True,
        "benchmark_id": "nexus-sf-final-all-candidate-live-compare-v1",
        "description": "Internal live Flash+Nexus current-primary vs all ready candidate skill comparison. Not a public benchmark.",
        "status": "PASS" if tasks and not blockers else "BLOCKED",
        "summary": {
            "task_count": len(tasks),
            "capability_count": len({task["category"] for task in tasks}),
            "ready_candidate_count": len(classifications),
            "live_eligible_candidate_count": sum(1 for row in classifications if row["live_eligible"]),
            "filtered_candidate_count": sum(1 for row in classifications if not row["live_eligible"]),
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
        },
        "tasks": tasks,
    }
    status_report = {
        "schema": "nexus.sf_final_all_candidate_live_compare_skill_status.v1",
        "summary": {
            "skill_count": len(status_rows),
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
        },
        "skills": status_rows,
    }
    matrix = {
        "schema": "nexus.sf_final_all_candidate_live_compare_matrix.v1",
        "status": "PASS" if matrix_rows and not blockers else "BLOCKED",
        "summary": {
            "capability_count": len(tasks),
            "ready_candidate_count": len(classifications),
            "live_eligible_capability_count": len({row["capability"] for row in classifications if row["live_eligible"]}),
            "live_eligible_candidate_count": sum(1 for row in classifications if row["live_eligible"]),
            "filtered_candidate_count": sum(1 for row in classifications if not row["live_eligible"]),
            "task_count": len(tasks),
            "baseline_arm_count": len(baselines),
            "candidate_arm_count": sum(1 for row in matrix_rows if row.get("arm_id") == "candidate_skill"),
            "row_count": len(matrix_rows),
            "model": model,
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
            "blocker_count": len(blockers),
        },
        "blockers": blockers,
        "rows": matrix_rows,
    }
    classification_report = {
        "schema": "nexus.sf_final_264_candidate_classification.v1",
        "status": "PASS" if classifications else "BLOCKED",
        "summary": {
            "ready_candidate_count": len(classifications),
            "capability_count": len({row["capability"] for row in classifications}),
            "live_eligible_candidate_count": sum(1 for row in classifications if row["live_eligible"]),
            "filtered_candidate_count": sum(1 for row in classifications if not row["live_eligible"]),
            "primary_role_count": sum(1 for row in classifications if row["classification"] == "LIVE_ELIGIBLE_PRIMARY_ROLE"),
            "support_role_count": sum(1 for row in classifications if row["classification"] == "LIVE_ELIGIBLE_SUPPORT_ROLE"),
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
        },
        "capability_need_profiles": {
            capability: _need_profile(capability)
            for capability in sorted({row["capability"] for row in classifications})
        },
        "candidates": classifications,
    }
    write_json(tasks_output, task_manifest)
    write_json(status_output, status_report)
    write_json(matrix_output, matrix)
    write_json(classification_output, classification_report)
    return matrix


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build SF final all-candidate live Flash+Nexus matrix.")
    parser.add_argument("--compare-report", default=str(DEFAULT_COMPARE_REPORT))
    parser.add_argument("--tasks-output", default=str(DEFAULT_TASKS))
    parser.add_argument("--skill-status-output", default=str(DEFAULT_STATUS))
    parser.add_argument("--matrix-output", default=str(DEFAULT_MATRIX))
    parser.add_argument("--classification-output", default=str(DEFAULT_CLASSIFICATION))
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args(argv)
    matrix = build_sf_final_live_compare_artifacts(
        compare_report=read_json(args.compare_report),
        tasks_output=Path(args.tasks_output),
        status_output=Path(args.skill_status_output),
        matrix_output=Path(args.matrix_output),
        classification_output=Path(args.classification_output),
        model=args.model,
    )
    print(json.dumps({"status": matrix["status"], **matrix["summary"]}, ensure_ascii=False, sort_keys=True))
    return 0 if matrix["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
