from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Any

from nexus.engine.model_output_sandbox import (
    SandboxError,
    argument_file_roots,
    interpreter_readable_roots,
    run_model_argv,
)

KNOWN_BUGGY_SYMBOLS: tuple[str, ...] = (
    "view(NdarrayMixin)",
)


@dataclass(frozen=True)
class IsolatedVerifierRequest:
    task_id: str
    workspace_path: str
    verifier_command: tuple[str, ...]
    timeout_sec: float = 30.0
    verifier_allowed: bool = False
    # Extra read-only roots for the sandboxed run (e.g. a sealed oracle outside the workspace).
    readable_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class IsolatedVerifierReceipt:
    task_id: str
    verifier_status: str
    exit_code: int | None
    stdout_tail: str
    stderr_tail: str
    verifier_error: str
    verifier_allowed: bool
    public_claim_allowed: bool = False
    production_ready: bool = False
    tests_run: list[dict[str, Any]] | None = None


def run_isolated_verifier(request: IsolatedVerifierRequest) -> IsolatedVerifierReceipt:
    if not request.verifier_allowed:
        return IsolatedVerifierReceipt(
            task_id=request.task_id,
            verifier_status="blocked",
            exit_code=None,
            stdout_tail="",
            stderr_tail="",
            verifier_error="verifier_not_allowed",
            verifier_allowed=False,
        )
        
    if not isinstance(request.verifier_command, tuple):
        return IsolatedVerifierReceipt(
            task_id=request.task_id,
            verifier_status="blocked",
            exit_code=None,
            stdout_tail="",
            stderr_tail="",
            verifier_error="verifier_command_must_be_tuple",
            verifier_allowed=True,
        )
        
    if not request.verifier_command:
        return IsolatedVerifierReceipt(
            task_id=request.task_id,
            verifier_status="blocked",
            exit_code=None,
            stdout_tail="",
            stderr_tail="",
            verifier_error="verifier_command_empty",
            verifier_allowed=True,
        )
        
    try:
        # The workspace holds a model-written patch: run its tests under the OS sandbox (no
        # network, writes only in the workspace, allowlisted env). No barrier, no run (#2936).
        res = run_model_argv(
            request.verifier_command,
            work_dir=request.workspace_path,
            timeout=request.timeout_sec,
            readable=(
                *interpreter_readable_roots(request.verifier_command[0]),
                *argument_file_roots(request.verifier_command),
                *request.readable_paths,
            ),
            text=False,
        )
        
        stdout_str = res.stdout.decode("utf-8", errors="replace")[-1000:]
        stderr_str = res.stderr.decode("utf-8", errors="replace")[-1000:]
        
        status = "pass" if res.returncode == 0 else "fail"
        
        return IsolatedVerifierReceipt(
            task_id=request.task_id,
            verifier_status=status,
            exit_code=res.returncode,
            stdout_tail=stdout_str,
            stderr_tail=stderr_str,
            verifier_error="",
            verifier_allowed=True,
        )
    except SandboxError as e:
        return IsolatedVerifierReceipt(
            task_id=request.task_id,
            verifier_status="blocked",
            exit_code=None,
            stdout_tail="",
            stderr_tail="",
            verifier_error=f"verifier_sandbox_unavailable: {e}",
            verifier_allowed=True,
        )
    except subprocess.TimeoutExpired as e:
        stdout_str = (e.stdout or b"").decode("utf-8", errors="replace")[-1000:]
        stderr_str = (e.stderr or b"").decode("utf-8", errors="replace")[-1000:]
        return IsolatedVerifierReceipt(
            task_id=request.task_id,
            verifier_status="blocked",
            exit_code=None,
            stdout_tail=stdout_str,
            stderr_tail=stderr_str,
            verifier_error=f"verifier_timeout: execution exceeded {request.timeout_sec} seconds",
            verifier_allowed=True,
        )
    except Exception as e:
        return IsolatedVerifierReceipt(
            task_id=request.task_id,
            verifier_status="blocked",
            exit_code=None,
            stdout_tail="",
            stderr_tail="",
            verifier_error=f"verifier_internal_error: {str(e)}",
            verifier_allowed=True,
        )


def compute_semantic_correctness(receipt: IsolatedVerifierReceipt) -> bool:
    if not receipt.tests_run:
        return False
    if receipt.verifier_status != "pass":
        return False
    output = receipt.stdout_tail + receipt.stderr_tail
    for symbol in KNOWN_BUGGY_SYMBOLS:
        if symbol in output:
            return False
    return True
