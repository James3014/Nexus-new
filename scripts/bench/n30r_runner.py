"""N30R paired-arm benchmark runner.

Supports bare and core arms with injected providers.
Dry-run mode for contract testing.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.bench.n30r_contracts import (
    N30RAttemptReceipt,
    N30RArmSpec,
    N30RTaskSpec,
    N30RTerminalStatus,
    sha256_hex,
    sha256_str,
)
from scripts.bench.n30r_arm_adapters import (
    ArmRunResult,
    ProviderFn,
    run_bare_arm,
    _read_fixture_source,
)
from scripts.bench.n30r_real_core_bridge import (
    RealCoreBridgeResult,
    REAL_CORE_ARM_ID,
    run_real_core_bridge,
)


# ---------------------------------------------------------------------------
# Arm registry
# ---------------------------------------------------------------------------

ARMS = {
    "N30R_A_7B_BARE": N30RArmSpec(
        arm_id="N30R_A_7B_BARE",
        model_provider="ollama",
        model_name="qwen2.5-coder:7b-instruct",
        model_parameters={"param_count": 7_000_000_000},
        nexus_enabled=False,
        core_armor_enabled=False,
        additional_capability="",
        arm_config_sha256=sha256_str("bare_arm_config"),
    ),
    "N30R_B_7B_REAL_CORE": N30RArmSpec(
        arm_id="N30R_B_7B_REAL_CORE",
        model_provider="ollama",
        model_name="qwen2.5-coder:7b-instruct",
        model_parameters={"param_count": 7_000_000_000},
        nexus_enabled=True,
        core_armor_enabled=True,
        additional_capability="",
        arm_config_sha256=sha256_str("real_core_arm_config"),
    ),
}


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def _materialize_task(task_dict: dict) -> N30RTaskSpec:
    """Materialize task from manifest dict, computing hashes."""
    fixture_path = Path(__file__).resolve().parents[2] / task_dict["source_relpath"]
    mod = {}
    exec(fixture_path.read_text(), mod)

    source_code = mod["ORIGINAL"]
    verifier = tuple(task_dict["verifier_command"])

    source_sha = sha256_str(source_code)
    verifier_sha = sha256_str(json.dumps(list(verifier)))
    env_sha = sha256_str(f"python3:{sys.version}")
    bundle_sha = sha256_str(f"{source_sha}:{verifier_sha}:{env_sha}")

    return N30RTaskSpec(
        task_id=task_dict["task_id"],
        split=task_dict["split"],
        source_relpath=task_dict["source_relpath"],
        source_sha256=source_sha,
        task_statement=task_dict["task_statement"],
        expected_failure_signature=task_dict["expected_failure_signature"],
        verifier_command=verifier,
        verifier_contract_sha256=verifier_sha,
        environment_sha256=env_sha,
        task_bundle_sha256=bundle_sha,
        golden_patch_sha256="",
        golden_patch_private_ref="",
        original_verifier_expected="FAIL",
        golden_verifier_expected="PASS",
    )


def _build_attempt_receipt(
    task: N30RTaskSpec,
    arm: N30RArmSpec,
    result,
    run_id: str,
    seed: int,
    trial_index: int,
) -> N30RAttemptReceipt:
    """Build attempt receipt from ArmRunResult or RealCoreBridgeResult."""
    base = N30RAttemptReceipt(
        run_id=run_id,
        task_id=task.task_id,
        trial_index=trial_index,
        seed=seed,
        arm_id=arm.arm_id,
        provider_requested=arm.model_provider,
        provider_actual=result.provider_actual,
        model_requested=arm.model_name,
        model_actual=result.model_actual,
        model_parameters_sha256=sha256_str(json.dumps(arm.model_parameters, sort_keys=True)),
        task_bundle_sha256=task.task_bundle_sha256,
        source_sha256=task.source_sha256,
        verifier_contract_sha256=task.verifier_contract_sha256,
        environment_sha256=task.environment_sha256,
        arm_config_sha256=arm.arm_config_sha256,
        rendered_prompt_sha256=sha256_str(result.prompt_text),
        model_call_started=result.wall_time_sec > 0,
        model_response_received=bool(result.raw_output),
        raw_output_sha256=sha256_str(result.raw_output) if result.raw_output else "",
        raw_output_length=len(result.raw_output),
        patch_sha256=sha256_str(result.patch_text) if result.patch_text else "",
        patch_length=len(result.patch_text),
        apply_status=result.apply_status,
        verifier_status=result.verifier_status,
        terminal_status=result.terminal_status,
        timeout_limit_sec=120.0,
        wall_time_sec=result.wall_time_sec,
        timed_out=result.timed_out,
        timeout_stage=result.timeout_stage,
        candidate_isolated=True,
        trust_mismatch=False,
        receipt_complete=True,
    )
    # Add production path fields if present (RealCoreBridgeResult)
    if hasattr(result, "execution_path_kind"):
        base.execution_path_kind = result.execution_path_kind
        base.planner_called = result.planner_called
        base.planner_version = result.planner_version
        base.route_truth_source = result.route_truth_source
        base.signal_snapshot_sha256 = result.signal_snapshot_sha256
        base.selected_executor = result.selected_executor
        base.execution_topology = result.execution_topology
        base.local_model_executor_called = result.local_model_executor_called
        base.production_local_path_used = result.production_local_path_used
        base.legacy_adapter_called = result.legacy_adapter_called
        base.model_call_count = result.model_call_count
        base.semantic_retry_count = result.semantic_retry_count
        base.candidate_id = result.candidate_id
        base.candidate_workspace_id = result.candidate_workspace_id
        base.production_receipt_sha256 = result.production_receipt_sha256
    else:
        # Bare arm defaults
        base.execution_path_kind = "bare_direct_provider"
    return base


def run_benchmark(
    manifest_path: str,
    arm_ids: list[str],
    task_ids: Optional[list[str]],
    trials: int,
    seeds: list[int],
    output_path: str,
    provider: ProviderFn,
    dry_run: bool = False,
) -> list[dict]:
    """Run the benchmark and return receipt dicts."""
    manifest = json.loads(Path(manifest_path).read_text())
    tasks_raw = manifest["tasks"]

    if task_ids:
        tasks_raw = [t for t in tasks_raw if t["task_id"] in task_ids]

    # Validate arms
    for aid in arm_ids:
        if aid not in ARMS:
            raise ValueError(f"Unknown arm: {aid}. Valid: {list(ARMS.keys())}")

    # Validate no duplicate task IDs
    seen_ids = set()
    for t in tasks_raw:
        if t["task_id"] in seen_ids:
            raise ValueError(f"Duplicate task: {t['task_id']}")
        seen_ids.add(t["task_id"])

    # Materialize tasks
    tasks = [_materialize_task(t) for t in tasks_raw]

    receipts = []
    run_id = f"run_{int(time.time())}"

    for task in tasks:
        for trial_idx, seed in enumerate(seeds):
            for arm_id in arm_ids:
                arm = ARMS[arm_id]

                if dry_run:
                    result = ArmRunResult(
                        terminal_status="DRY_RUN",
                        raw_output="",
                        patch_text="",
                        apply_status="none",
                        verifier_status="not_run",
                        wall_time_sec=0.0,
                        timed_out=False,
                        timeout_stage="",
                        model_actual=arm.model_name,
                        provider_actual=arm.model_provider,
                        prompt_text="dry_run_prompt",
                    )
                elif arm_id == "N30R_A_7B_BARE":
                    result = run_bare_arm(task, arm, provider, seed, trial_idx, run_id)
                elif arm_id == "N30R_B_7B_REAL_CORE":
                    result = run_real_core_bridge(task, arm, provider, seed, trial_idx, run_id)
                else:
                    raise ValueError(f"Unhandled arm: {arm_id}")

                receipt = _build_attempt_receipt(task, arm, result, run_id, seed, trial_idx)
                receipt_dict = {
                    "run_id": receipt.run_id,
                    "task_id": receipt.task_id,
                    "trial_index": receipt.trial_index,
                    "seed": receipt.seed,
                    "arm_id": receipt.arm_id,
                    "provider_requested": receipt.provider_requested,
                    "provider_actual": receipt.provider_actual,
                    "model_requested": receipt.model_requested,
                    "model_actual": receipt.model_actual,
                    "model_parameters_sha256": receipt.model_parameters_sha256,
                    "task_bundle_sha256": receipt.task_bundle_sha256,
                    "source_sha256": receipt.source_sha256,
                    "verifier_contract_sha256": receipt.verifier_contract_sha256,
                    "environment_sha256": receipt.environment_sha256,
                    "arm_config_sha256": receipt.arm_config_sha256,
                    "rendered_prompt_sha256": receipt.rendered_prompt_sha256,
                    "model_call_started": receipt.model_call_started,
                    "model_response_received": receipt.model_response_received,
                    "raw_output_sha256": receipt.raw_output_sha256,
                    "raw_output_length": receipt.raw_output_length,
                    "patch_sha256": receipt.patch_sha256,
                    "patch_length": receipt.patch_length,
                    "apply_status": receipt.apply_status,
                    "verifier_status": receipt.verifier_status,
                    "terminal_status": receipt.terminal_status,
                    "timeout_limit_sec": receipt.timeout_limit_sec,
                    "wall_time_sec": receipt.wall_time_sec,
                    "timed_out": receipt.timed_out,
                    "timeout_stage": receipt.timeout_stage,
                    "candidate_isolated": receipt.candidate_isolated,
                    "trust_mismatch": receipt.trust_mismatch,
                    "receipt_complete": receipt.receipt_complete,
                    # N30R-R1 production path fields
                    "execution_path_kind": receipt.execution_path_kind,
                    "planner_called": receipt.planner_called,
                    "planner_version": receipt.planner_version,
                    "route_truth_source": receipt.route_truth_source,
                    "signal_snapshot_sha256": receipt.signal_snapshot_sha256,
                    "selected_executor": receipt.selected_executor,
                    "execution_topology": receipt.execution_topology,
                    "local_model_executor_called": receipt.local_model_executor_called,
                    "production_local_path_used": receipt.production_local_path_used,
                    "legacy_adapter_called": receipt.legacy_adapter_called,
                    "model_call_count": receipt.model_call_count,
                    "semantic_retry_count": receipt.semantic_retry_count,
                    "candidate_id": receipt.candidate_id,
                    "candidate_workspace_id": receipt.candidate_workspace_id,
                    "production_receipt_sha256": receipt.production_receipt_sha256,
                }
                receipts.append(receipt_dict)

    # Write output
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        for r in receipts:
            f.write(json.dumps(r) + "\n")

    return receipts


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--arms", required=True, help="Comma-separated arm IDs")
    parser.add_argument("--task-ids", default=None, help="Comma-separated task IDs")
    parser.add_argument("--trials", type=int, default=1)
    parser.add_argument("--seeds", default="3001", help="Comma-separated seeds")
    parser.add_argument("--output", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--summarize", default=None, help="Summarize existing JSONL")
    parser.add_argument("--public-jsonl", default=None)
    parser.add_argument("--summary-json", default=None)
    args = parser.parse_args()

    if args.summarize:
        # Just read and re-output
        rows = [json.loads(l) for l in Path(args.summarize).read_text().splitlines() if l.strip()]
        if args.public_jsonl:
            Path(args.public_jsonl).parent.mkdir(parents=True, exist_ok=True)
            Path(args.public_jsonl).write_text("\n".join(json.dumps(r) for r in rows) + "\n")
        if args.summary_json:
            summary = {
                "total_rows": len(rows),
                "solved": sum(1 for r in rows if r.get("terminal_status") == "VERIFIED_SOLVE"),
                "failed": sum(1 for r in rows if r.get("terminal_status") == "VERIFIED_FAIL"),
                "timeout": sum(1 for r in rows if r.get("terminal_status") == "MODEL_TIMEOUT"),
                "infra_invalid": sum(1 for r in rows if r.get("terminal_status") == "INFRA_INVALID"),
            }
            Path(args.summary_json).write_text(json.dumps(summary, indent=2))
        print(f"Summarized {len(rows)} rows")
        return

    arm_ids = [a.strip() for a in args.arms.split(",")]
    task_ids = [t.strip() for t in args.task_ids.split(",")] if args.task_ids else None
    seeds = [int(s.strip()) for s in args.seeds.split(",")]

    def _noop_provider(model: str, system_prompt: str, user_prompt: str) -> str:
        return ""

    receipts = run_benchmark(
        manifest_path=args.manifest,
        arm_ids=arm_ids,
        task_ids=task_ids,
        trials=args.trials,
        seeds=seeds,
        output_path=args.output,
        provider=_noop_provider if args.dry_run else None,
        dry_run=args.dry_run,
    )
    print(f"Wrote {len(receipts)} receipts to {args.output}")


if __name__ == "__main__":
    main()
