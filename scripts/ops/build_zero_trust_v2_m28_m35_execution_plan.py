#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nexus.learning.skill_fit_closure import read_json, write_json


DEFAULT_RUNNER_MATRIX = Path("docs/reports/NEXUS_ZERO_TRUST_V2_BEHAVIOR_RUNNER_MATRIX_2026-05-21.json")
DEFAULT_M20_M27 = Path("docs/reports/NEXUS_ZERO_TRUST_V2_M20_M27_COMPLETION_2026-05-21.json")
DEFAULT_OUTPUT = Path("docs/reports/NEXUS_ZERO_TRUST_V2_M28_M35_EXECUTION_PLAN_2026-05-21.json")


def _replace_arg(command: list[str], flag: str, value: str) -> list[str]:
    updated = list(command)
    if flag in updated:
        index = updated.index(flag)
        if index + 1 < len(updated):
            updated[index + 1] = value
            return updated
    return [*updated, flag, value]


def _p0_ready_adapters(runner_matrix: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item
        for item in runner_matrix.get("adapters", []) or []
        if isinstance(item, dict)
        and item.get("priority") == "P0"
        and item.get("status") == "READY_FOR_PHYSICAL_BEHAVIOR_RUN"
        and item.get("command")
    ]


def _candidate_sort_key(item: dict[str, Any]) -> tuple[int, str, str]:
    # Prefer the acceptance/sandbox path as the first canary because it is a safety-gate capability.
    capability = str(item.get("capability_id") or "")
    preferred = 0 if capability in {"sandbox_replay", "policy_capability_gate"} else 1
    return (preferred, capability, str(item.get("skill_id") or ""))


def build_zero_trust_v2_m28_m35_execution_plan(*, runner_matrix: dict[str, Any], m20_m27: dict[str, Any]) -> dict[str, Any]:
    p0_ready = sorted(_p0_ready_adapters(runner_matrix), key=_candidate_sort_key)
    selected = p0_ready[0] if p0_ready else {}
    command = list(selected.get("command") or [])
    runner_env = selected.get("runner_env") if isinstance(selected.get("runner_env"), dict) else {}
    capability_id = str(selected.get("capability_id") or "")
    skill_id = str(selected.get("skill_id") or "")
    base_output_dir = f".nexus/reports/zero_trust_v2_behavior/{capability_id}/{skill_id}"
    preflight_command = [*_replace_arg(command, "--output-dir", f"{base_output_dir}/preflight"), "--preflight-only"] if command else []
    run_plan = []
    for run_index in range(1, 4):
        output_dir = f"{base_output_dir}/run-{run_index:02d}"
        run_plan.append(
            {
                "run_index": run_index,
                "run_id": f"ztv2-m29-{capability_id}-{skill_id}-{run_index:02d}",
                "command": _replace_arg(command, "--output-dir", output_dir) if command else [],
                "runner_env": runner_env,
                "expected_evidence_bundle": f"{output_dir}/evidence_bundle.json",
                "signed_receipt_required": True,
                "promotion_credit_allowed": False,
            }
        )
    existing_receipts = [
        item["expected_evidence_bundle"]
        for item in run_plan
        if item["expected_evidence_bundle"] and Path(item["expected_evidence_bundle"]).exists()
    ]
    m20_summary = m20_m27.get("summary", {}) if isinstance(m20_m27.get("summary"), dict) else {}
    ready_physical = int(m20_summary.get("m21_ready_for_physical_behavior_run_count") or 0)
    return {
        "schema": "nexus.zero_trust_v2.m28_m35_execution_plan.v1",
        "status": "PASS",
        "created_at": datetime.now(UTC).isoformat(),
        "source_runner_matrix": str(DEFAULT_RUNNER_MATRIX),
        "source_m20_m27": str(DEFAULT_M20_M27),
        "summary": {
            "m28_selected_canary_count": 1 if selected else 0,
            "m28_preflight_ready": bool(preflight_command),
            "m29_signed_behavior_run_plan_count": len([item for item in run_plan if item["command"]]),
            "m29_signed_behavior_executed_count": len(existing_receipts),
            "m30_existing_receipt_bundle_count": len(existing_receipts),
            "m30_clean_v2_receipt_count": 0,
            "m31_manual_apply_trial_ready_count": 0,
            "m32_canary_apply_ready": False,
            "m33_p0_ready_for_execution_count": len(p0_ready),
            "m34_p1_p2_ready_for_execution_count": max(0, ready_physical - len(p0_ready)),
            "m35_v1_path_closure_plan_ready": False,
            "v2_unification_complete": False,
            "runtime_mutation_allowed": False,
            "automatic_apply_allowed": False,
            "public_benchmark_allowed": False,
            "promotion_credit_allowed": False,
        },
        "selected_canary_candidate": {
            "capability_id": capability_id,
            "skill_id": skill_id,
            "priority": str(selected.get("priority") or ""),
            "task_ref": selected.get("task_ref") if isinstance(selected.get("task_ref"), dict) else {},
        },
        "m28_preflight_hook": {
            "hook_status": "READY_TO_RUN_PRECHECK" if preflight_command else "BLOCKED",
            "command": preflight_command,
            "runner_env": runner_env,
            "claim_boundary": "Preflight may validate runner/task wiring only; it is not V2 promotion evidence.",
        },
        "m29_three_run_plan": run_plan,
        "m30_receipt_import_gate": {
            "required_receipt_bundle_count": 3,
            "existing_receipt_bundle_count": len(existing_receipts),
            "existing_receipt_bundles": existing_receipts,
            "status": "BLOCKED",
            "blockers": ["missing_signed_v2_behavior_receipts"],
        },
        "m31_manual_apply_trial_gate": {
            "status": "BLOCKED",
            "blockers": ["no_manual_apply_ready_candidate"],
            "operator_ack_required": True,
        },
        "m32_canary_apply_rollback_gate": {
            "status": "BLOCKED",
            "rollback_target": "restore_v1_runtime_overlay_primary",
            "post_apply_smoke_required": True,
            "blockers": ["manual_apply_trial_not_ready"],
        },
        "m35_v1_path_closure_gate": {
            "status": "BLOCKED",
            "requires_34_capabilities_v2_ready": True,
            "blockers": ["v2_unification_incomplete"],
        },
        "claim_boundary": [
            "This plan prepares M28-M35 execution commands and gates only.",
            "No command in this artifact has been executed by the builder.",
            "Runtime mutation and V1 path closure remain blocked until signed V2 receipts and manual apply gates pass.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Zero-Trust V2 M28-M35 execution plan.")
    parser.add_argument("--runner-matrix", default=str(DEFAULT_RUNNER_MATRIX))
    parser.add_argument("--m20-m27", default=str(DEFAULT_M20_M27))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)
    result = build_zero_trust_v2_m28_m35_execution_plan(
        runner_matrix=read_json(args.runner_matrix),
        m20_m27=read_json(args.m20_m27),
    )
    write_json(args.output, result)
    print(json.dumps({"status": result["status"], "output": args.output, **result["summary"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
