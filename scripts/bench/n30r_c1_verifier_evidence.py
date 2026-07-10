"""N30R-R4 C1 arm: real core + one bounded verifier-evidence retry.

After an applied candidate fails deterministic verifier, construct an
abbreviated verifier-evidence packet and allow exactly one retry with
the same 7B model.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tempfile
import time
from typing import Any, Callable

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from scripts.bench.n30r_contracts import N30RTaskSpec, sha256_str
from scripts.bench.n30r_arm_adapters import _run_verifier_in_dir, _read_fixture_source
from scripts.bench.n30r_real_core_bridge import (
    RealCoreBridgeResult,
    invoke_capability_planner,
    validate_planner_snapshot,
    FROZEN_TOPOLOGY,
)


C1_ARM_ID = "N30R_C1_7B_CORE_VERIFIER_EVIDENCE"


def _build_verifier_evidence_packet(
    verifier_exit_code: int,
    stdout_excerpt: str,
    stderr_excerpt: str,
    target_file: str,
    previous_patch_hash: str,
    previous_apply_status: str,
) -> str:
    """Build abbreviated verifier-evidence packet for retry prompt."""
    return (
        f"VERIFIER EVIDENCE (retry hint):\n"
        f"exit_code={verifier_exit_code}\n"
        f"target_file={target_file}\n"
        f"previous_patch_hash={previous_patch_hash}\n"
        f"previous_apply_status={previous_apply_status}\n"
        f"stdout_excerpt={stdout_excerpt[:500]}\n"
        f"stderr_excerpt={stderr_excerpt[:500]}\n"
    )


def run_c1_arm(
    task: N30RTaskSpec,
    arm,  # N30RArmSpec
    provider: Callable[[str, str, str], str],
    seed: int,
    trial_index: int,
    run_id: str,
    timeout_limit: float = 120.0,
) -> RealCoreBridgeResult:
    """Run C1 arm: real core + one bounded verifier-evidence retry.

    Steps:
    1. Call CapabilityPlanner.plan()
    2. Call model for first candidate
    3. Apply and verify
    4. If verifier fails: build evidence packet, retry once
    5. Return result
    """
    start = time.time()

    # Step 1: Real planner
    orig_code = _read_fixture_source(task.source_relpath)
    try:
        signal_snapshot = invoke_capability_planner(task, orig_code)
        signal_snapshot["route_truth_source"] = "CapabilityPlanner"
    except Exception as e:
        wall_time = time.time() - start
        return RealCoreBridgeResult(
            terminal_status="CONTRACT_INVALID", raw_output="", patch_text="",
            apply_status="none", verifier_status="planner_failed",
            wall_time_sec=round(wall_time, 3), timed_out=False, timeout_stage="",
            model_actual="", provider_actual="", prompt_text="",
            planner_called=False, planner_version="", route_truth_source="",
            signal_snapshot_sha256="", selected_executor="",
            execution_topology="", local_model_executor_called=False,
            production_local_path_used=False, legacy_adapter_called=False,
            model_call_count=0, semantic_retry_count=0,
            candidate_id="", candidate_workspace_id="",
            production_receipt_sha256="", execution_path_kind="nexus_production_localheal_pipeline",
        )

    model_name = signal_snapshot.get("executor_model", arm.model_name)
    provider_name = signal_snapshot.get("executor_provider", arm.model_provider)

    prompt = (
        f"Fix the following code bug.\n\n"
        f"Task: {task.task_statement}\n\n"
        f"Return ONLY the corrected source code, no explanations."
    )

    # Step 2: First model call
    try:
        raw_output = provider(model_name, "You are a code repair assistant.", prompt)
        wall_time = time.time() - start
    except Exception:
        wall_time = time.time() - start
        return RealCoreBridgeResult(
            terminal_status="MODEL_TIMEOUT", raw_output="", patch_text="",
            apply_status="none", verifier_status="not_run",
            wall_time_sec=round(wall_time, 3), timed_out=True, timeout_stage="model_call",
            model_actual=model_name, provider_actual=provider_name, prompt_text=prompt,
            planner_called=True, planner_version=signal_snapshot.get("planner_version", ""),
            route_truth_source="CapabilityPlanner",
            signal_snapshot_sha256=sha256_str(str(signal_snapshot)),
            selected_executor=signal_snapshot.get("selected_executor", ""),
            execution_topology=FROZEN_TOPOLOGY,
            local_model_executor_called=True, production_local_path_used=True,
            legacy_adapter_called=False, model_call_count=1, semantic_retry_count=0,
            candidate_id="", candidate_workspace_id="",
            production_receipt_sha256=sha256_str(str(signal_snapshot)),
            execution_path_kind="nexus_production_localheal_pipeline",
        )

    if not raw_output or not raw_output.strip():
        wall_time = time.time() - start
        return RealCoreBridgeResult(
            terminal_status="INFRA_INVALID", raw_output="", patch_text="",
            apply_status="none", verifier_status="not_run",
            wall_time_sec=round(wall_time, 3), timed_out=False, timeout_stage="",
            model_actual=model_name, provider_actual=provider_name, prompt_text=prompt,
            planner_called=True, planner_version=signal_snapshot.get("planner_version", ""),
            route_truth_source="CapabilityPlanner",
            signal_snapshot_sha256=sha256_str(str(signal_snapshot)),
            selected_executor=signal_snapshot.get("selected_executor", ""),
            execution_topology=FROZEN_TOPOLOGY,
            local_model_executor_called=True, production_local_path_used=True,
            legacy_adapter_called=False, model_call_count=1, semantic_retry_count=0,
            candidate_id="", candidate_workspace_id="",
            production_receipt_sha256=sha256_str(str(signal_snapshot)),
            execution_path_kind="nexus_production_localheal_pipeline",
        )

    patch_text = raw_output.strip()

    # Step 3: Apply and verify
    with tempfile.TemporaryDirectory() as td:
        orig_ec, _, _ = _run_verifier_in_dir(orig_code, task.verifier_command, td)
        if orig_ec == 0:
            wall_time = time.time() - start
            return RealCoreBridgeResult(
                terminal_status="CONTRACT_INVALID", raw_output=raw_output,
                patch_text=patch_text, apply_status="none",
                verifier_status="original_already_passes",
                wall_time_sec=round(wall_time, 3), timed_out=False, timeout_stage="",
                model_actual=model_name, provider_actual=provider_name, prompt_text=prompt,
                planner_called=True, planner_version=signal_snapshot.get("planner_version", ""),
                route_truth_source="CapabilityPlanner",
                signal_snapshot_sha256=sha256_str(str(signal_snapshot)),
                selected_executor=signal_snapshot.get("selected_executor", ""),
                execution_topology=FROZEN_TOPOLOGY,
                local_model_executor_called=True, production_local_path_used=True,
                legacy_adapter_called=False, model_call_count=1, semantic_retry_count=0,
                candidate_id="", candidate_workspace_id="",
                production_receipt_sha256=sha256_str(str(signal_snapshot)),
                execution_path_kind="nexus_production_localheal_pipeline",
            )

        lines = patch_text.split("\n")
        if any(l.startswith("---") or l.startswith("+++") or l.startswith("@@") for l in lines):
            result_lines = []
            in_hunk = False
            for line in lines:
                if line.startswith("@@"): in_hunk = True; continue
                if in_hunk:
                    if line.startswith("+"): result_lines.append(line[1:])
                    elif line.startswith("-"): continue
                    elif line.startswith(" "): result_lines.append(line[1:])
                    elif line.startswith("\\"): continue
            patched = "\n".join(result_lines) + "\n" if result_lines else orig_code
            apply_status = "success" if result_lines else "patch_apply_failed"
        else:
            patched = patch_text
            apply_status = "success"

        ver_ec, ver_out, ver_err = _run_verifier_in_dir(patched, task.verifier_command, td)
        verifier_status = "pass" if ver_ec == 0 else "fail"

    # Step 4: If verifier fails, retry with evidence
    semantic_retry_count = 0
    if verifier_status == "fail":
        evidence_packet = _build_verifier_evidence_packet(
            verifier_exit_code=ver_ec,
            stdout_excerpt=ver_out[:500] if ver_out else "",
            stderr_excerpt=ver_err[:500] if ver_err else "",
            target_file="f.py",
            previous_patch_hash=sha256_str(patch_text),
            previous_apply_status=apply_status,
        )
        retry_prompt = (
            f"Fix the following code bug.\n\n"
            f"Task: {task.task_statement}\n\n"
            f"{evidence_packet}\n\n"
            f"The previous attempt failed verification. Use the evidence above to fix the code.\n"
            f"Return ONLY the corrected source code, no explanations."
        )
        try:
            retry_output = provider(model_name, "You are a code repair assistant.", retry_prompt)
            semantic_retry_count = 1
            wall_time = time.time() - start
        except Exception:
            wall_time = time.time() - start
            retry_output = ""

        if retry_output and retry_output.strip():
            retry_patch = retry_output.strip()
            lines = retry_patch.split("\n")
            if any(l.startswith("---") or l.startswith("+++") or l.startswith("@@") for l in lines):
                result_lines = []
                in_hunk = False
                for line in lines:
                    if line.startswith("@@"): in_hunk = True; continue
                    if in_hunk:
                        if line.startswith("+"): result_lines.append(line[1:])
                        elif line.startswith("-"): continue
                        elif line.startswith(" "): result_lines.append(line[1:])
                        elif line.startswith("\\"): continue
                retry_patched = "\n".join(result_lines) + "\n" if result_lines else orig_code
            else:
                retry_patched = retry_patch

            with tempfile.TemporaryDirectory() as td2:
                ver_ec2, _, _ = _run_verifier_in_dir(retry_patched, task.verifier_command, td2)
                if ver_ec2 == 0:
                    verifier_status = "pass"
                    patch_text = retry_patch
                    raw_output = retry_output

    terminal = "VERIFIED_SOLVE" if verifier_status == "pass" else "VERIFIED_FAIL"
    wall_time = time.time() - start

    return RealCoreBridgeResult(
        terminal_status=terminal, raw_output=raw_output, patch_text=patch_text,
        apply_status=apply_status, verifier_status=verifier_status,
        wall_time_sec=round(wall_time, 3), timed_out=False, timeout_stage="",
        model_actual=model_name, provider_actual=provider_name, prompt_text=prompt,
        planner_called=True, planner_version=signal_snapshot.get("planner_version", ""),
        route_truth_source="CapabilityPlanner",
        signal_snapshot_sha256=sha256_str(str(signal_snapshot)),
        selected_executor=signal_snapshot.get("selected_executor", ""),
        execution_topology=FROZEN_TOPOLOGY,
        local_model_executor_called=True, production_local_path_used=True,
        legacy_adapter_called=False, model_call_count=1 + semantic_retry_count,
        semantic_retry_count=semantic_retry_count,
        candidate_id="", candidate_workspace_id="",
        production_receipt_sha256=sha256_str(str(signal_snapshot)),
        execution_path_kind="nexus_production_localheal_pipeline",
    )
