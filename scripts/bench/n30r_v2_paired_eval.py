#!/usr/bin/env python3
"""N30R V2 Paired Bare/Core Evaluation Harness.

Supports three modes:
  --plan-only     : Validate manifest and generate schedule, no provider calls
  --validate-only : Validate results JSONL against manifest
  --run           : Execute paired evaluation (requires V1 merge)

Usage:
    python scripts/bench/n30r_v2_paired_eval.py \\
        --manifest docs/bench/n30r/v2_four_task_paired_manifest.json \\
        --plan-only \\
        --json-out /tmp/n30r_v2_plan.json

    python scripts/bench/n30r_v2_paired_eval.py \\
        --manifest docs/bench/n30r/v2_four_task_paired_manifest.json \\
        --results <results.jsonl> \\
        --validate-only \\
        --json-out <validation.json>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.bench.n30r_contracts import sha256_str


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_ARM_IDS = {"N30R_A_7B_BARE", "N30R_B_7B_REAL_CORE"}

VALID_TERMINAL_STATUSES = {
    "VERIFIED_SOLVE", "VERIFIED_FAIL", "MODEL_TIMEOUT",
    "PROVIDER_ERROR", "PROTOCOL_INVALID", "APPLY_INVALID",
    "VERIFIER_INVALID", "CONTRACT_INVALID", "INFRA_INVALID",
    "DRY_RUN",
}

VALID_ORACLE_STATUSES = {
    "FULL_ARMOR_PATH_ACCEPTED",
    "DETERMINISTIC_PATH_ACCEPTED_LIVE_PENDING",
    "ORACLE_READY_PRODUCER_ARTIFACT_PENDING",
    "REJECTED_CONTRACT_INVALID",
    "REJECTED_EVIDENCE_INVALID",
    "REJECTED_HASH_CHAIN_INVALID",
    "NOT_APPLICABLE",
}

EFFECTIVENESS_STATUSES = {
    "V2_NOT_RUN", "V2_INVALID", "V2_VALID_NO_UPLIFT",
    "V2_DIRECTIONAL_UPLIFT", "V2_DIRECTIONAL_REGRESSION",
}

FAILURE_FAMILIES = {
    "provider", "timeout", "protocol", "candidate",
    "apply", "verifier", "contract", "infra",
}


# ---------------------------------------------------------------------------
# Manifest loading
# ---------------------------------------------------------------------------

def load_manifest(path: str) -> dict[str, Any]:
    """Load and validate manifest."""
    with open(path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    if manifest.get("schema") != "n30r_v2_paired_manifest_v1":
        raise ValueError(f"Unknown manifest schema: {manifest.get('schema')}")

    tasks = manifest.get("tasks", [])
    if len(tasks) != 4:
        raise ValueError(f"Expected 4 tasks, got {len(tasks)}")

    for task in tasks:
        tid = task.get("task_id", "")
        if not tid:
            raise ValueError("Task missing task_id")
        for field in ("source_fixture_sha256", "verifier_contract_sha256", "task_seed"):
            if not task.get(field):
                raise ValueError(f"Task {tid} missing {field}")
        order = task.get("execution_order", [])
        if len(order) != 2:
            raise ValueError(f"Task {tid} execution_order must have 2 arms")
        if set(order) != VALID_ARM_IDS:
            raise ValueError(f"Task {tid} execution_order has invalid arms: {order}")

    return manifest


# ---------------------------------------------------------------------------
# Plan mode
# ---------------------------------------------------------------------------

def plan_only(manifest: dict[str, Any]) -> dict[str, Any]:
    """Generate paired execution schedule without provider calls."""
    tasks = manifest["tasks"]
    schedule = []
    total_rows = 0

    for task in tasks:
        task_id = task["task_id"]
        order = task["execution_order"]
        seed = task["task_seed"]

        for idx, arm_id in enumerate(order):
            row = {
                "task_id": task_id,
                "arm_id": arm_id,
                "trial_index": 0,
                "task_seed": seed,
                "execution_order_index": idx,
                "source_fixture_sha256": task["source_fixture_sha256"],
                "verifier_contract_sha256": task["verifier_contract_sha256"],
                "task_statement_sha256": task["task_statement_sha256"],
            }
            schedule.append(row)
            total_rows += 1

    # Verify alternating pattern
    orders = [t["execution_order"] for t in tasks]
    alternating = True
    for i in range(len(orders) - 1):
        if orders[i] == orders[i + 1]:
            alternating = False
            break

    return {
        "status": "PLAN_READY",
        "experiment_id": manifest.get("experiment_id", ""),
        "total_tasks": len(tasks),
        "total_scheduled_rows": total_rows,
        "alternating_pattern": alternating,
        "execution_orders": [[t["task_id"], t["execution_order"]] for t in tasks],
        "schedule": schedule,
        "provider_calls": 0,
        "live_model_calls": 0,
        "arms": manifest.get("arms", {}),
        "claim_boundary": manifest.get("claim_boundary", {}),
    }


# ---------------------------------------------------------------------------
# Row validation
# ---------------------------------------------------------------------------

def validate_row(
    row: dict[str, Any],
    task_map: dict[str, dict[str, Any]],
    manifest: dict[str, Any],
) -> list[str]:
    """Validate a single result row. Returns list of issues (empty = valid)."""
    issues = []

    # Required fields
    required = [
        "task_id", "arm_id", "trial_index", "task_seed",
        "model_requested", "model_actual", "provider_actual",
        "task_statement_sha256", "source_fixture_sha256", "verifier_contract_sha256",
        "execution_completed", "contract_valid",
        "model_call_count", "model_response_received", "raw_output_length",
        "candidate_hash", "apply_status",
        "verifier_reached", "verifier_status",
        "semantic_retry_count", "wall_time_sec",
        "terminal_status", "solved",
    ]
    for field in required:
        if field not in row:
            issues.append(f"missing_field:{field}")

    # Arm ID
    arm_id = row.get("arm_id", "")
    if arm_id not in VALID_ARM_IDS:
        issues.append(f"invalid_arm_id:{arm_id}")

    # Terminal status
    ts = row.get("terminal_status", "")
    if ts not in VALID_TERMINAL_STATUSES:
        issues.append(f"invalid_terminal_status:{ts}")

    # Model identity
    model_req = row.get("model_requested", "")
    model_act = row.get("model_actual", "")
    provider_act = row.get("provider_actual", "")
    if model_req and model_act and model_req != model_act:
        issues.append(f"model_identity_mismatch:{model_req}!={model_act}")
    if provider_act and provider_act not in ("ollama", ""):
        issues.append(f"unexpected_provider:{provider_act}")

    # Task hash match
    task_id = row.get("task_id", "")
    task_def = task_map.get(task_id)
    if task_def:
        if row.get("source_fixture_sha256") != task_def.get("source_fixture_sha256"):
            issues.append("source_fixture_hash_mismatch")
        if row.get("verifier_contract_sha256") != task_def.get("verifier_contract_sha256"):
            issues.append("verifier_contract_hash_mismatch")
        if row.get("task_seed") != task_def.get("task_seed"):
            issues.append("task_seed_mismatch")

    # Solved rules
    solved = row.get("solved", False)
    verifier_reached = row.get("verifier_reached", False)
    verifier_status = row.get("verifier_status", "")

    if solved and ts != "VERIFIED_SOLVE":
        issues.append("solved_true_but_not_verified_solve")
    if ts == "VERIFIED_SOLVE" and not verifier_reached:
        issues.append("verified_solve_without_verifier_reached")
    if ts == "VERIFIED_SOLVE" and verifier_status != "pass":
        issues.append("verified_solve_without_verifier_pass")
    if ts == "VERIFIED_FAIL" and not verifier_reached:
        issues.append("verified_fail_without_verifier_reached")

    # Candidate isolation
    candidate_isolated = row.get("candidate_isolated", False)
    candidate_hash = row.get("candidate_hash", "")
    if candidate_isolated and not candidate_hash:
        issues.append("candidate_isolated_with_empty_hash")

    # Apply success
    apply_status = row.get("apply_status", "")
    if apply_status in ("success", "applied") and not candidate_hash:
        issues.append("apply_success_with_empty_candidate")

    # Timeout inference
    timed_out = row.get("timed_out", False)
    timeout_stage = row.get("timeout_stage", "")
    if timed_out and not timeout_stage:
        issues.append("timed_out_without_timeout_stage")

    # Core oracle
    if arm_id == "N30R_B_7B_REAL_CORE":
        oracle_status = row.get("armor_oracle_status", "")
        if not oracle_status:
            issues.append("core_missing_oracle_status")
        elif oracle_status in ("REJECTED_CONTRACT_INVALID", "REJECTED_EVIDENCE_INVALID",
                               "REJECTED_HASH_CHAIN_INVALID"):
            issues.append(f"core_oracle_rejected:{oracle_status}")

    return issues


# ---------------------------------------------------------------------------
# Validate results mode
# ---------------------------------------------------------------------------

def validate_results(
    manifest: dict[str, Any],
    results_path: str,
) -> dict[str, Any]:
    """Validate results JSONL against manifest."""
    tasks = manifest["tasks"]
    task_map = {t["task_id"]: t for t in tasks}

    rows = []
    with open(results_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))

    # Check row count
    expected_rows = len(tasks) * 2
    row_count_valid = len(rows) == expected_rows

    # Check each task has exactly 2 arms
    task_arm_counts: dict[str, set[str]] = {}
    for row in rows:
        tid = row.get("task_id", "")
        aid = row.get("arm_id", "")
        if tid not in task_arm_counts:
            task_arm_counts[tid] = set()
        task_arm_counts[tid].add(aid)

    complete_pairs = all(
        len(arms) == 2 and arms == VALID_ARM_IDS
        for arms in task_arm_counts.values()
    )

    # Validate each row
    all_issues: list[dict[str, Any]] = []
    valid_rows = 0
    invalid_rows = 0

    for row in rows:
        issues = validate_row(row, task_map, manifest)
        if issues:
            invalid_rows += 1
            all_issues.append({
                "task_id": row.get("task_id", ""),
                "arm_id": row.get("arm_id", ""),
                "issues": issues,
            })
        else:
            valid_rows += 1

    # Compute metrics if all valid
    metrics = {}
    effectiveness = "V2_INVALID"

    if valid_rows == expected_rows and row_count_valid and complete_pairs:
        metrics = compute_metrics(rows, task_map)
        effectiveness = classify_effectiveness(metrics, rows, task_map)

    return {
        "status": "VALIDATED" if not all_issues else "INVALID",
        "total_rows": len(rows),
        "expected_rows": expected_rows,
        "row_count_valid": row_count_valid,
        "complete_pairs": complete_pairs,
        "valid_rows": valid_rows,
        "invalid_rows": invalid_rows,
        "issues": all_issues,
        "metrics": metrics,
        "effectiveness": effectiveness,
    }


# ---------------------------------------------------------------------------
# Metrics computation
# ---------------------------------------------------------------------------

def compute_metrics(
    rows: list[dict[str, Any]],
    task_map: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Compute paired metrics from validated rows."""
    bare_rows = [r for r in rows if r.get("arm_id") == "N30R_A_7B_BARE"]
    core_rows = [r for r in rows if r.get("arm_id") == "N30R_B_7B_REAL_CORE"]

    def _rate(rows: list, key: str) -> float:
        if not rows:
            return 0.0
        return sum(1 for r in rows if r.get(key)) / len(rows)

    def _mean(rows: list, key: str) -> float:
        vals = [r.get(key, 0) for r in rows if isinstance(r.get(key), (int, float))]
        return sum(vals) / len(vals) if vals else 0.0

    def _sum(rows: list, key: str) -> int:
        return sum(r.get(key, 0) for r in rows if isinstance(r.get(key), (int, float)))

    bare_solves = sum(1 for r in bare_rows if r.get("solved"))
    core_solves = sum(1 for r in core_rows if r.get("solved"))

    # Paired outcome matrix
    task_solves: dict[str, dict[str, bool]] = {}
    for r in rows:
        tid = r.get("task_id", "")
        aid = r.get("arm_id", "")
        if tid not in task_solves:
            task_solves[tid] = {}
        task_solves[tid][aid] = r.get("solved", False)

    both_solve = 0
    bare_only = 0
    core_only = 0
    neither = 0
    for tid, arms in task_solves.items():
        b = arms.get("N30R_A_7B_BARE", False)
        c = arms.get("N30R_B_7B_REAL_CORE", False)
        if b and c:
            both_solve += 1
        elif b and not c:
            bare_only += 1
        elif c and not b:
            core_only += 1
        else:
            neither += 1

    # Failure family distribution
    failure_families: dict[str, int] = {f: 0 for f in FAILURE_FAMILIES}
    for r in rows:
        ts = r.get("terminal_status", "")
        if ts == "MODEL_TIMEOUT":
            failure_families["timeout"] += 1
        elif ts == "PROVIDER_ERROR":
            failure_families["provider"] += 1
        elif ts in ("PROTOCOL_INVALID",):
            failure_families["protocol"] += 1
        elif ts == "APPLY_INVALID":
            failure_families["apply"] += 1
        elif ts == "VERIFIER_INVALID":
            failure_families["verifier"] += 1
        elif ts == "CONTRACT_INVALID":
            failure_families["contract"] += 1
        elif ts == "INFRA_INVALID":
            failure_families["infra"] += 1

    return {
        "total_tasks": len(task_map),
        "valid_pairs": len(task_solves),
        "bare_verified_solves": bare_solves,
        "core_verified_solves": core_solves,
        "solve_delta": core_solves - bare_solves,
        "bare_model_response_rate": _rate(bare_rows, "model_response_received"),
        "core_model_response_rate": _rate(core_rows, "model_response_received"),
        "bare_protocol_parse_rate": _rate(bare_rows, "protocol_parse_success"),
        "core_protocol_parse_rate": _rate(core_rows, "protocol_parse_success"),
        "bare_candidate_rate": _rate(bare_rows, "candidate_hash"),
        "core_candidate_rate": _rate(core_rows, "candidate_hash"),
        "bare_apply_success_rate": _rate(bare_rows, "apply_status"),
        "core_apply_success_rate": _rate(core_rows, "apply_status"),
        "bare_verifier_reach_rate": _rate(bare_rows, "verifier_reached"),
        "core_verifier_reach_rate": _rate(core_rows, "verifier_reached"),
        "bare_retry_count": _sum(bare_rows, "semantic_retry_count"),
        "core_retry_count": _sum(core_rows, "semantic_retry_count"),
        "bare_mean_wall_time": _mean(bare_rows, "wall_time_sec"),
        "core_mean_wall_time": _mean(core_rows, "wall_time_sec"),
        "bare_total_model_calls": _sum(bare_rows, "model_call_count"),
        "core_total_model_calls": _sum(core_rows, "model_call_count"),
        "model_call_delta": _sum(core_rows, "model_call_count") - _sum(bare_rows, "model_call_count"),
        "wall_time_delta": _mean(core_rows, "wall_time_sec") - _mean(bare_rows, "wall_time_sec"),
        "paired_matrix": {
            "both_solve": both_solve,
            "bare_only_solve": bare_only,
            "core_only_solve": core_only,
            "neither_solve": neither,
        },
        "failure_families": failure_families,
    }


def classify_effectiveness(
    metrics: dict[str, Any],
    rows: list[dict[str, Any]],
    task_map: dict[str, dict[str, Any]],
) -> str:
    """Classify effectiveness from metrics."""
    if not metrics:
        return "V2_NOT_RUN"

    valid_pairs = metrics.get("valid_pairs", 0)
    if valid_pairs < len(task_map):
        return "V2_INVALID"

    # Check core oracle acceptance
    core_rows = [r for r in rows if r.get("arm_id") == "N30R_B_7B_REAL_CORE"]
    for r in core_rows:
        oracle = r.get("armor_oracle_status", "")
        if oracle in ("REJECTED_CONTRACT_INVALID", "REJECTED_EVIDENCE_INVALID",
                       "REJECTED_HASH_CHAIN_INVALID"):
            return "V2_INVALID"

    delta = metrics.get("solve_delta", 0)
    if delta > 0:
        return "V2_DIRECTIONAL_UPLIFT"
    elif delta < 0:
        return "V2_DIRECTIONAL_REGRESSION"
    else:
        return "V2_VALID_NO_UPLIFT"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="N30R V2 Paired Evaluation Harness")
    parser.add_argument("--manifest", required=True, help="Path to V2 paired manifest")
    parser.add_argument("--plan-only", action="store_true", help="Generate schedule without execution")
    parser.add_argument("--validate-only", action="store_true", help="Validate results JSONL")
    parser.add_argument("--results", help="Path to results JSONL for validation")
    parser.add_argument("--json-out", help="Path to write output JSON")
    parser.add_argument("--run", action="store_true", help="Execute paired evaluation")
    parser.add_argument("--provider", help="Provider name for run mode")
    parser.add_argument("--model", help="Model name for run mode")
    parser.add_argument("--jsonl-out", help="Path to write results JSONL for run mode")
    parser.add_argument("--summary-out", help="Path to write summary JSON for run mode")
    args = parser.parse_args()

    manifest = load_manifest(args.manifest)

    if args.plan_only:
        result = plan_only(manifest)
        if args.json_out:
            os.makedirs(os.path.dirname(args.json_out) or ".", exist_ok=True)
            with open(args.json_out, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2)
            print(f"Written: {args.json_out}")
        print(json.dumps(result, indent=2))
        return

    if args.validate_only:
        if not args.results:
            parser.error("--results is required for --validate-only")
        result = validate_results(manifest, args.results)
        if args.json_out:
            os.makedirs(os.path.dirname(args.json_out) or ".", exist_ok=True)
            with open(args.json_out, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2)
            print(f"Written: {args.json_out}")
        print(json.dumps(result, indent=2))
        return

    if args.run:
        print("RUN_MODE_BLOCKED_UNTIL_V1_MERGE")
        print("Plan mode and validation mode are ready.")
        print("Live execution requires V1 production path merge.")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
