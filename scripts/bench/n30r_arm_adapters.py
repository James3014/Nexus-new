"""N30R arm adapters — bare and core arm implementations.

Defines how each arm invokes a model and applies patches.
No live model calls in this module — providers are injected.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from typing import Any, Callable, Optional

sys.path.insert(0, str(os.path.join(os.path.dirname(__file__), "..", "..")))

from scripts.bench.n30r_contracts import (
    N30RAttemptReceipt,
    N30RArmSpec,
    N30RTaskSpec,
    N30RTerminalStatus,
    sha256_hex,
    sha256_str,
)


@dataclass
class ArmRunResult:
    terminal_status: str
    raw_output: str
    patch_text: str
    apply_status: str
    verifier_status: str
    wall_time_sec: float
    timed_out: bool
    timeout_stage: str
    model_actual: str
    provider_actual: str
    prompt_text: str


ProviderFn = Callable[[str, str, str], str]  # (model, system_prompt, user_prompt) -> response


def _run_verifier_in_dir(source_code: str, verifier_command: tuple[str, ...], work_dir: str) -> tuple[int, str, str]:
    """Write source to f.py, run verifier, return (exit_code, stdout, stderr)."""
    src = os.path.join(work_dir, "f.py")
    with open(src, "w") as fh:
        fh.write(source_code)
    result = subprocess.run(
        list(verifier_command),
        capture_output=True,
        text=True,
        cwd=work_dir,
        timeout=30,
    )
    return result.returncode, result.stdout, result.stderr


def _apply_patch_simple(source_code: str, patch_text: str) -> tuple[str, str]:
    """Minimal patch application: if patch contains a unified diff, try to apply.
    Returns (new_source, apply_status)."""
    if not patch_text.strip():
        return source_code, "no_patch"
    # Try to extract the full file from patch if it's a complete replacement
    lines = patch_text.strip().split("\n")
    # If patch looks like a full file (no diff markers), use it directly
    if not any(l.startswith("---") or l.startswith("+++") or l.startswith("@@") for l in lines):
        return patch_text.strip(), "success"
    # Simple diff application: extract b/ lines
    result_lines = []
    in_hunk = False
    for line in lines:
        if line.startswith("@@"):
            in_hunk = True
            continue
        if in_hunk:
            if line.startswith("+"):
                result_lines.append(line[1:])
            elif line.startswith("-"):
                continue
            elif line.startswith(" "):
                result_lines.append(line[1:])
            elif line.startswith("\\"):
                continue
    if result_lines:
        return "\n".join(result_lines) + "\n", "success"
    return source_code, "patch_apply_failed"


def run_bare_arm(
    task: N30RTaskSpec,
    arm: N30RArmSpec,
    provider: ProviderFn,
    seed: int,
    trial_index: int,
    run_id: str,
    timeout_limit: float = 120.0,
) -> ArmRunResult:
    """Run bare arm: direct model call, no Nexus features."""
    import time

    prompt = (
        f"Fix the following code bug.\n\n"
        f"Task: {task.task_statement}\n\n"
        f"Return ONLY the corrected source code, no explanations."
    )

    start = time.time()
    try:
        raw_output = provider(arm.model_name, "You are a code repair assistant.", prompt)
        wall_time = time.time() - start
        model_actual = arm.model_name
        provider_actual = arm.model_provider
    except Exception as e:
        wall_time = time.time() - start
        return ArmRunResult(
            terminal_status=N30RTerminalStatus.MODEL_TIMEOUT.value,
            raw_output="",
            patch_text="",
            apply_status="none",
            verifier_status="not_run",
            wall_time_sec=round(wall_time, 3),
            timed_out=True,
            timeout_stage="model_call",
            model_actual="",
            provider_actual="",
            prompt_text=prompt,
        )

    if not raw_output or not raw_output.strip():
        return ArmRunResult(
            terminal_status=N30RTerminalStatus.INFRA_INVALID.value,
            raw_output="",
            patch_text="",
            apply_status="none",
            verifier_status="not_run",
            wall_time_sec=round(wall_time, 3),
            timed_out=False,
            timeout_stage="",
            model_actual=model_actual,
            provider_actual=provider_actual,
            prompt_text=prompt,
        )

    patch_text = raw_output.strip()
    with tempfile.TemporaryDirectory() as td:
        # Verify original fails
        orig_code = _read_fixture_source(task.source_relpath)
        orig_ec, _, _ = _run_verifier_in_dir(orig_code, task.verifier_command, td)
        if orig_ec == 0:
            return ArmRunResult(
                terminal_status=N30RTerminalStatus.CONTRACT_INVALID.value,
                raw_output=raw_output,
                patch_text=patch_text,
                apply_status="none",
                verifier_status="original_already_passes",
                wall_time_sec=round(wall_time, 3),
                timed_out=False,
                timeout_stage="",
                model_actual=model_actual,
                provider_actual=provider_actual,
                prompt_text=prompt,
            )

        patched, apply_status = _apply_patch_simple(orig_code, patch_text)
        ver_ec, ver_out, ver_err = _run_verifier_in_dir(patched, task.verifier_command, td)
        verifier_status = "pass" if ver_ec == 0 else "fail"

    terminal = N30RTerminalStatus.VERIFIED_SOLVE.value if verifier_status == "pass" else N30RTerminalStatus.VERIFIED_FAIL.value

    return ArmRunResult(
        terminal_status=terminal,
        raw_output=raw_output,
        patch_text=patch_text,
        apply_status=apply_status,
        verifier_status=verifier_status,
        wall_time_sec=round(wall_time, 3),
        timed_out=False,
        timeout_stage="",
        model_actual=model_actual,
        provider_actual=provider_actual,
        prompt_text=prompt,
    )


def run_core_arm(
    task: N30RTaskSpec,
    arm: N30RArmSpec,
    provider: ProviderFn,
    seed: int,
    trial_index: int,
    run_id: str,
    timeout_limit: float = 120.0,
) -> ArmRunResult:
    """Run core arm: Nexus armor with planner-owned signal snapshot.

    For N30R, the core arm adds assertion-grounded problem statement
    and anchor shaping but runs the same 7B model.
    """
    import time

    # Core arm adds assertion-grounded problem statement
    prompt = (
        f"You are a code repair assistant with assertion-grounded analysis.\n\n"
        f"Task: {task.task_statement}\n"
        f"Expected failure: {task.expected_failure_signature}\n"
        f"Target: fix the code so the verifier passes.\n\n"
        f"Return ONLY the corrected source code, no explanations."
    )

    start = time.time()
    try:
        raw_output = provider(arm.model_name, "You are a code repair assistant.", prompt)
        wall_time = time.time() - start
        model_actual = arm.model_name
        provider_actual = arm.model_provider
    except Exception as e:
        wall_time = time.time() - start
        return ArmRunResult(
            terminal_status=N30RTerminalStatus.MODEL_TIMEOUT.value,
            raw_output="",
            patch_text="",
            apply_status="none",
            verifier_status="not_run",
            wall_time_sec=round(wall_time, 3),
            timed_out=True,
            timeout_stage="model_call",
            model_actual="",
            provider_actual="",
            prompt_text=prompt,
        )

    if not raw_output or not raw_output.strip():
        return ArmRunResult(
            terminal_status=N30RTerminalStatus.INFRA_INVALID.value,
            raw_output="",
            patch_text="",
            apply_status="none",
            verifier_status="not_run",
            wall_time_sec=round(wall_time, 3),
            timed_out=False,
            timeout_stage="",
            model_actual=model_actual,
            provider_actual=provider_actual,
            prompt_text=prompt,
        )

    patch_text = raw_output.strip()
    with tempfile.TemporaryDirectory() as td:
        orig_code = _read_fixture_source(task.source_relpath)
        orig_ec, _, _ = _run_verifier_in_dir(orig_code, task.verifier_command, td)
        if orig_ec == 0:
            return ArmRunResult(
                terminal_status=N30RTerminalStatus.CONTRACT_INVALID.value,
                raw_output=raw_output,
                patch_text=patch_text,
                apply_status="none",
                verifier_status="original_already_passes",
                wall_time_sec=round(wall_time, 3),
                timed_out=False,
                timeout_stage="",
                model_actual=model_actual,
                provider_actual=provider_actual,
                prompt_text=prompt,
            )

        patched, apply_status = _apply_patch_simple(orig_code, patch_text)
        ver_ec, ver_out, ver_err = _run_verifier_in_dir(patched, task.verifier_command, td)
        verifier_status = "pass" if ver_ec == 0 else "fail"

    terminal = N30RTerminalStatus.VERIFIED_SOLVE.value if verifier_status == "pass" else N30RTerminalStatus.VERIFIED_FAIL.value

    return ArmRunResult(
        terminal_status=terminal,
        raw_output=raw_output,
        patch_text=patch_text,
        apply_status=apply_status,
        verifier_status=verifier_status,
        wall_time_sec=round(wall_time, 3),
        timed_out=False,
        timeout_stage="",
        model_actual=model_actual,
        provider_actual=provider_actual,
        prompt_text=prompt,
    )


def _read_fixture_source(source_relpath: str) -> str:
    """Read original source from fixture."""
    fixture_path = os.path.join(os.path.dirname(__file__), "..", "..", source_relpath)
    mod = {}
    exec(open(fixture_path).read(), mod)
    return mod.get("ORIGINAL", "")
